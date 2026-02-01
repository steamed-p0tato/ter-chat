"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                           MYSTIKO CHAT SERVER                                  ║
║                     Multi-Room Chat with SQLite Storage                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import socket
import threading
import json
import time
import traceback
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config import (
    SERVER_HOST, SERVER_PORT, BUFFER_SIZE,
    MAX_ROOM_NAME_LENGTH, MIN_ROOM_NAME_LENGTH, MAX_ROOMS_PER_USER,
    MAX_MESSAGE_LENGTH, CHAT_HISTORY_LIMIT
)
from database import db


class ChatServer:
    def __init__(self, host=SERVER_HOST, port=SERVER_PORT):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Runtime data (not persisted)
        self.clients = {}  # {socket: {'username': str, 'address': tuple, 'room': str or None}}
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Console
        self.console = Console()
        
        # Client buffers for incomplete messages
        self.client_buffers = {}  # {socket: str}

    # ============== Logging ==============

    def log(self, level, message):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        color_map = {
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CONNECTION': 'cyan',
            'MESSAGE': 'blue',
            'AUTH': 'magenta',
            'ROOM': 'yellow',
            'DEBUG': 'dim white',
            'DATABASE': 'bright_blue'
        }
        color = color_map.get(level, 'white')
        self.console.print(f"[dim]{timestamp}[/] [{color}][{level:^10}][/{color}] {message}")

    # ============== Network Operations ==============

    def send_to_client(self, client_socket, data):
        """Send JSON data to a client"""
        try:
            message = json.dumps(data) + '\n'
            client_socket.sendall(message.encode('utf-8'))
            return True
        except Exception as e:
            self.log("ERROR", f"Send error: {e}")
            return False

    def receive_from_client(self, client_socket):
        """Receive JSON data from a client with proper buffering"""
        try:
            if client_socket not in self.client_buffers:
                self.client_buffers[client_socket] = ""
            
            while True:
                if '\n' in self.client_buffers[client_socket]:
                    line, self.client_buffers[client_socket] = \
                        self.client_buffers[client_socket].split('\n', 1)
                    if line.strip():
                        try:
                            data = json.loads(line.strip())
                            return data
                        except json.JSONDecodeError as e:
                            self.log("ERROR", f"JSON decode error: {e}")
                            continue
                
                data = client_socket.recv(BUFFER_SIZE).decode('utf-8')
                if not data:
                    return None
                
                self.client_buffers[client_socket] += data
                
        except Exception as e:
            self.log("ERROR", f"Receive error: {e}")
            return None

    def broadcast_to_room(self, room_name, message_data, exclude_socket=None, save_to_db=False):
        """Broadcast a message to all users in a room"""
        targets = []
        with self.lock:
            for client_socket, info in list(self.clients.items()):
                if info.get('room') == room_name and client_socket != exclude_socket:
                    targets.append(client_socket)
        
        for client_socket in targets:
            self.send_to_client(client_socket, message_data)
        
        # Optionally save to database
        if save_to_db and message_data.get('type') in ['message', 'system']:
            msg_type = message_data.get('type', 'message')
            username = message_data.get('username', 'System')
            content = message_data.get('message', '')
            db.save_message(room_name, username, content, msg_type)

    def get_room_members(self, room_name):
        """Get list of usernames in a room"""
        members = []
        with self.lock:
            for info in self.clients.values():
                if info.get('room') == room_name:
                    members.append(info['username'])
        return members

    def get_user_count_in_room(self, room_name):
        """Get number of users in a room"""
        return len(self.get_room_members(room_name))

    # ============== Authentication ==============

    def authenticate_client(self, client_socket, address):
        """Handle client authentication"""
        try:
            self.log("AUTH", f"Waiting for auth data from {address}")
            
            auth_data = self.receive_from_client(client_socket)
            
            if not auth_data:
                self.log("AUTH", f"No auth data received from {address}")
                return None
            
            action = auth_data.get('action')
            username = auth_data.get('username', '').strip()
            password = auth_data.get('password', '')
            
            self.log("AUTH", f"Auth attempt: action={action}, username='{username}' from {address}")
            
            if not username or not password:
                self.log("AUTH", "Missing username or password")
                self.send_to_client(client_socket, {
                    'status': 'error',
                    'message': 'Username and password are required'
                })
                return None
            
            if action == 'login':
                return self.handle_login(client_socket, username, password)
            elif action == 'register':
                return self.handle_register(client_socket, username, password)
            else:
                self.log("AUTH", f"Invalid action: {action}")
                self.send_to_client(client_socket, {
                    'status': 'error',
                    'message': f'Invalid action: {action}'
                })
                return None
                
        except Exception as e:
            self.log("ERROR", f"Auth error: {e}")
            traceback.print_exc()
            return None

    def handle_login(self, client_socket, username, password):
        """Handle user login"""
        self.log("AUTH", f"Login attempt for: '{username}'")
        
        # Verify credentials using database
        actual_username = db.verify_user(username, password)
        
        if actual_username is None:
            # Check if user exists
            if db.user_exists(username):
                self.log("AUTH", f"Login failed: wrong password for '{username}'")
                self.send_to_client(client_socket, {
                    'status': 'error',
                    'message': 'Incorrect password'
                })
            else:
                self.log("AUTH", f"Login failed: user '{username}' not found")
                self.send_to_client(client_socket, {
                    'status': 'error',
                    'message': 'User not found. Please register first.'
                })
            return None
        
        # Check if already logged in
        with self.lock:
            for client_info in self.clients.values():
                if client_info['username'].lower() == actual_username.lower():
                    self.log("AUTH", f"Login failed: '{username}' already logged in")
                    self.send_to_client(client_socket, {
                        'status': 'error',
                        'message': 'Already logged in from another session'
                    })
                    return None
        
        self.send_to_client(client_socket, {
            'status': 'success',
            'message': f'Welcome back, {actual_username}!'
        })
        self.log("AUTH", f"Login successful: '{actual_username}'")
        return actual_username

    def handle_register(self, client_socket, username, password):
        """Handle user registration"""
        self.log("AUTH", f"Registration attempt for: '{username}'")
        
        # Validate username length
        if len(username) < 3:
            self.log("AUTH", f"Registration failed: username '{username}' too short")
            self.send_to_client(client_socket, {
                'status': 'error',
                'message': 'Username must be at least 3 characters'
            })
            return None
        
        if len(username) > 20:
            self.log("AUTH", f"Registration failed: username '{username}' too long")
            self.send_to_client(client_socket, {
                'status': 'error',
                'message': 'Username must be 20 characters or less'
            })
            return None
        
        # Validate alphanumeric
        if not username.isalnum():
            self.log("AUTH", f"Registration failed: username '{username}' not alphanumeric")
            self.send_to_client(client_socket, {
                'status': 'error',
                'message': 'Username must contain only letters and numbers'
            })
            return None
        
        # Validate password length
        if len(password) < 4:
            self.log("AUTH", f"Registration failed: password too short")
            self.send_to_client(client_socket, {
                'status': 'error',
                'message': 'Password must be at least 4 characters'
            })
            return None
        
        # Check if username exists
        if db.user_exists(username):
            self.log("AUTH", f"Registration failed: username '{username}' already exists")
            self.send_to_client(client_socket, {
                'status': 'error',
                'message': 'Username already exists'
            })
            return None
        
        # Create user
        if db.create_user(username, password):
            self.log("AUTH", f"Registration successful: '{username}'")
            self.log("DATABASE", f"New user created: '{username}'")
            self.send_to_client(client_socket, {
                'status': 'success',
                'message': f'Account created successfully! Welcome, {username}!'
            })
            return username
        else:
            self.send_to_client(client_socket, {
                'status': 'error',
                'message': 'Failed to create account'
            })
            return None

    # ============== Room Operations ==============

    def handle_create_room(self, client_socket, username, data):
        """Handle room creation"""
        room_name = data.get('room_name', '').strip()
        password = data.get('password')
        description = data.get('description', '').strip() or 'No description'
        
        # Check if trying to create private room
        if password:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': '🔒 Private rooms are coming soon! Stay tuned.'
            })
            return
        
        # Validate room name length
        if len(room_name) < MIN_ROOM_NAME_LENGTH:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': f'Room name must be at least {MIN_ROOM_NAME_LENGTH} characters'
            })
            return
        
        if len(room_name) > MAX_ROOM_NAME_LENGTH:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': f'Room name must be less than {MAX_ROOM_NAME_LENGTH} characters'
            })
            return
        
        # Validate room name characters
        if not room_name.replace(' ', '').replace('-', '').replace('_', '').isalnum():
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': 'Room name can only contain letters, numbers, spaces, hyphens, and underscores'
            })
            return
        
        # Check if room exists
        if db.room_exists(room_name):
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': 'A room with this name already exists'
            })
            return
        
        # Check room limit per user (admin exempt)
        if username.lower() != 'admin':
            user_room_count = db.count_user_rooms(username)
            if user_room_count >= MAX_ROOMS_PER_USER:
                self.send_to_client(client_socket, {
                    'type': 'error',
                    'message': f'You can only create {MAX_ROOMS_PER_USER} room(s). Delete an existing room first.'
                })
                return
        
        # Create room (always public for now)
        if db.create_room(room_name, username, None, description[:100]):
            self.send_to_client(client_socket, {
                'type': 'room_created',
                'room_name': room_name,
                'message': f'Room "{room_name}" created successfully!'
            })
            self.log("ROOM", f"Created: '{room_name}' by '{username}'")
            self.log("DATABASE", f"Room saved to database: '{room_name}'")
        else:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': 'Failed to create room'
            })

    def handle_list_rooms(self, client_socket, data):
        """Handle room listing request"""
        search_query = data.get('search', '').strip()
        
        rooms = db.get_all_rooms(search_query)
        
        rooms_list = []
        for room in rooms:
            rooms_list.append({
                'name': room['name'],
                'creator': room['creator'],
                'is_private': room['password'] is not None,
                'user_count': self.get_user_count_in_room(room['name']),
                'description': room.get('description', 'No description'),
                'created_at': room['created_at']
            })
        
        # Sort by user count (descending), then by name
        rooms_list.sort(key=lambda x: (-x['user_count'], x['name'].lower()))
        
        self.send_to_client(client_socket, {
            'type': 'room_list',
            'rooms': rooms_list
        })

    def handle_join_room(self, client_socket, username, data):
        """Handle joining a room"""
        room_name = data.get('room_name', '').strip()
        password = data.get('password')
        
        current_room = None
        
        # Get room from database
        room = db.get_room(room_name)
        
        if not room:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': f'Room "{room_name}" does not exist'
            })
            return
        
        # Check password if private room
        if room['password'] is not None:
            if password != room['password']:
                self.send_to_client(client_socket, {
                    'type': 'error',
                    'message': 'Incorrect room password'
                })
                return
        
        # Leave current room if in one
        with self.lock:
            if client_socket in self.clients:
                current_room = self.clients[client_socket].get('room')
                self.clients[client_socket]['room'] = room['name']  # Use actual name from DB
        
        # Notify old room (outside lock)
        if current_room:
            self.broadcast_to_room(current_room, {
                'type': 'system',
                'message': f'🚪 {username} left the room',
                'username': 'System',
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }, save_to_db=True)
        
        # Send success message
        self.send_to_client(client_socket, {
            'type': 'room_joined',
            'room_name': room['name'],
            'creator': room['creator'],
            'description': room.get('description', 'No description'),
            'message': f'Joined room "{room["name"]}"!'
        })
        
        # Send chat history
        self.send_chat_history(client_socket, room['name'])
        
        # Notify room members
        self.broadcast_to_room(room['name'], {
            'type': 'system',
            'message': f'👋 {username} joined the room!',
            'username': 'System',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }, exclude_socket=client_socket, save_to_db=True)
        
        # Send user list
        self.send_room_users(client_socket, room['name'])
        
        self.log("ROOM", f"'{username}' joined '{room['name']}'")

    def send_chat_history(self, client_socket, room_name):
        """Send chat history to a client"""
        messages = db.get_room_messages(room_name, CHAT_HISTORY_LIMIT)
        
        if messages:
            self.send_to_client(client_socket, {
                'type': 'chat_history',
                'room_name': room_name,
                'messages': messages,
                'count': len(messages)
            })
            self.log("DATABASE", f"Sent {len(messages)} history messages for '{room_name}'")

    def handle_leave_room(self, client_socket, username):
        """Handle leaving a room"""
        current_room = None
        
        with self.lock:
            if client_socket not in self.clients:
                return
            
            current_room = self.clients[client_socket].get('room')
            if not current_room:
                self.send_to_client(client_socket, {
                    'type': 'error',
                    'message': 'You are not in any room'
                })
                return
            
            self.clients[client_socket]['room'] = None
        
        # Notify room members (outside lock)
        self.broadcast_to_room(current_room, {
            'type': 'system',
            'message': f'🚪 {username} left the room',
            'username': 'System',
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }, save_to_db=True)
        
        self.send_to_client(client_socket, {
            'type': 'room_left',
            'message': f'Left room "{current_room}"'
        })
        
        self.log("ROOM", f"'{username}' left '{current_room}'")

    def handle_delete_room(self, client_socket, username, data):
        """Handle room deletion"""
        room_name = data.get('room_name', '').strip()
        
        sockets_to_notify = []
        
        # Get room from database
        room = db.get_room(room_name)
        
        if not room:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': f'Room "{room_name}" does not exist'
            })
            return
        
        # Check if user is creator or admin
        if room['creator'].lower() != username.lower() and username.lower() != 'admin':
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': 'Only the room creator can delete this room'
            })
            return
        
        # Collect sockets to notify and kick everyone
        with self.lock:
            for sock, info in self.clients.items():
                if info.get('room') and info['room'].lower() == room_name.lower():
                    info['room'] = None
                    sockets_to_notify.append(sock)
        
        # Delete the room from database
        if db.delete_room(room_name):
            # Notify all kicked users (outside lock)
            for sock in sockets_to_notify:
                self.send_to_client(sock, {
                    'type': 'room_deleted',
                    'message': f'Room "{room_name}" has been deleted by the creator'
                })
            
            self.send_to_client(client_socket, {
                'type': 'room_delete_success',
                'message': f'Room "{room_name}" has been deleted'
            })
            
            self.log("ROOM", f"Deleted: '{room_name}' by '{username}'")
            self.log("DATABASE", f"Room and messages deleted: '{room_name}'")
        else:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': 'Failed to delete room'
            })

    def send_room_users(self, client_socket, room_name):
        """Send list of users in a room"""
        members = self.get_room_members(room_name)
        self.send_to_client(client_socket, {
            'type': 'room_users',
            'room_name': room_name,
            'users': members
        })

    def handle_room_message(self, client_socket, username, data):
        """Handle a chat message in a room"""
        content = data.get('content', '').strip()
        
        if not content:
            return
        
        # Limit message length
        if len(content) > MAX_MESSAGE_LENGTH:
            content = content[:MAX_MESSAGE_LENGTH] + "..."
        
        with self.lock:
            if client_socket not in self.clients:
                return
            current_room = self.clients[client_socket].get('room')
        
        if not current_room:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': 'You must join a room to send messages'
            })
            return
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Save message to database
        db.save_message(current_room, username, content, 'message')
        
        # Broadcast to room (including sender)
        self.broadcast_to_room(current_room, {
            'type': 'message',
            'username': username,
            'message': content,
            'room': current_room,
            'timestamp': timestamp
        })
        
        self.log("MESSAGE", f"[{current_room}] {username}: {content[:50]}{'...' if len(content) > 50 else ''}")

    def handle_private_message(self, client_socket, username, data):
        """Handle private message"""
        target = data.get('target', '').strip()
        content = data.get('content', '').strip()
        
        if not target or not content:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': 'Invalid private message format'
            })
            return
        
        target_socket = None
        actual_target = None
        
        with self.lock:
            for sock, info in self.clients.items():
                if info['username'].lower() == target.lower():
                    target_socket = sock
                    actual_target = info['username']
                    break
        
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        if target_socket:
            self.send_to_client(target_socket, {
                'type': 'private',
                'from': username,
                'message': content,
                'timestamp': timestamp
            })
            self.send_to_client(client_socket, {
                'type': 'private_sent',
                'to': actual_target,
                'message': content,
                'timestamp': timestamp
            })
            self.log("MESSAGE", f"[PM] {username} -> {actual_target}: {content[:30]}...")
        else:
            self.send_to_client(client_socket, {
                'type': 'error',
                'message': f"User '{target}' is not online"
            })

    def handle_get_my_rooms(self, client_socket, username):
        """Get rooms created by this user"""
        rooms = db.get_rooms_by_creator(username)
        
        my_rooms = []
        for room in rooms:
            my_rooms.append({
                'name': room['name'],
                'is_private': room['password'] is not None,
                'user_count': self.get_user_count_in_room(room['name']),
                'created_at': room['created_at'],
                'description': room.get('description', 'No description')
            })
        
        self.send_to_client(client_socket, {
            'type': 'my_rooms',
            'rooms': my_rooms
        })

    # ============== Client Handler ==============

    def handle_client(self, client_socket, address):
        """Handle a connected client"""
        username = None
        
        try:
            # Initialize buffer for this client
            self.client_buffers[client_socket] = ""
            
            # Authenticate
            username = self.authenticate_client(client_socket, address)
            
            if not username:
                self.log("AUTH", f"Authentication failed for {address}")
                time.sleep(0.2)
                client_socket.close()
                return
            
            # Add to clients
            with self.lock:
                self.clients[client_socket] = {
                    'username': username,
                    'address': address,
                    'room': None
                }
            
            self.log("CONNECTION", f"'{username}' connected from {address[0]}:{address[1]}")
            
            # Main message loop
            while True:
                data = self.receive_from_client(client_socket)
                
                if not data:
                    self.log("CONNECTION", f"'{username}' connection closed")
                    break
                
                msg_type = data.get('type')
                
                if msg_type == 'create_room':
                    self.handle_create_room(client_socket, username, data)
                
                elif msg_type == 'list_rooms':
                    self.handle_list_rooms(client_socket, data)
                
                elif msg_type == 'join_room':
                    self.handle_join_room(client_socket, username, data)
                
                elif msg_type == 'leave_room':
                    self.handle_leave_room(client_socket, username)
                
                elif msg_type == 'delete_room':
                    self.handle_delete_room(client_socket, username, data)
                
                elif msg_type == 'message':
                    self.handle_room_message(client_socket, username, data)
                
                elif msg_type == 'private':
                    self.handle_private_message(client_socket, username, data)
                
                elif msg_type == 'get_room_users':
                    room_name = data.get('room_name')
                    if room_name:
                        self.send_room_users(client_socket, room_name)
                
                elif msg_type == 'get_my_rooms':
                    self.handle_get_my_rooms(client_socket, username)
                
                else:
                    self.log("WARNING", f"Unknown message type from '{username}': {msg_type}")
        
        except Exception as e:
            self.log("ERROR", f"Client error ({username or 'unknown'}): {e}")
            traceback.print_exc()
        
        finally:
            # Clean up
            current_room = None
            with self.lock:
                if client_socket in self.clients:
                    current_room = self.clients[client_socket].get('room')
                    del self.clients[client_socket]
                
                if client_socket in self.client_buffers:
                    del self.client_buffers[client_socket]
            
            if username and current_room:
                self.broadcast_to_room(current_room, {
                    'type': 'system',
                    'message': f'🔴 {username} disconnected',
                    'username': 'System',
                    'timestamp': datetime.now().strftime('%H:%M:%S')
                }, save_to_db=True)
            
            if username:
                self.log("CONNECTION", f"'{username}' disconnected")
            
            try:
                client_socket.close()
            except:
                pass

    # ============== Server Startup ==============

    def display_header(self):
        """Display server header"""
        self.console.clear()
        
        logo = """
[bold cyan]    ███╗   ███╗██╗   ██╗███████╗████████╗██╗██╗  ██╗ ██████╗ 
    ████╗ ████║╚██╗ ██╔╝██╔════╝╚══██╔══╝██║██║ ██╔╝██╔═══██╗
    ██╔████╔██║ ╚████╔╝ ███████╗   ██║   ██║█████╔╝ ██║   ██║
    ██║╚██╔╝██║  ╚██╔╝  ╚════██║   ██║   ██║██╔═██╗ ██║   ██║
    ██║ ╚═╝ ██║   ██║   ███████║   ██║   ██║██║  ██╗╚██████╔╝
    ╚═╝     ╚═╝   ╚═╝   ╚══════╝   ╚═╝   ╚═╝╚═╝  ╚═╝ ╚═════╝[/] 
        """
        
        self.console.print(logo)
        
        header = Panel(
            "[bold cyan]Mystiko Chat Server[/bold cyan]\n"
            "[dim]Multi-Room Chat with SQLite Persistent Storage[/dim]",
            title="🖥️  SERVER",
            border_style="cyan",
            padding=(0, 2)
        )
        self.console.print(header)
        
        # Stats table
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Address", f"{self.host}:{self.port}")
        table.add_row("Database", "mystiko.db (SQLite)")
        table.add_row("Registered Users", str(db.get_user_count()))
        table.add_row("Total Rooms", str(db.get_room_count()))
        table.add_row("Chat History", f"Last {CHAT_HISTORY_LIMIT} messages per room")
        
        self.console.print(Panel(table, title="📊 Server Info", border_style="green"))
        self.console.print("\n[bold]Server Logs:[/bold]")
        self.console.print("─" * 80)

    def start(self):
        """Start the server"""
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(10)
            
            self.display_header()
            self.log("INFO", f"Server started on {self.host}:{self.port}")
            self.log("DATABASE", "SQLite database initialized")
            self.log("INFO", "Waiting for connections...")
            
            while True:
                try:
                    client_socket, address = self.server_socket.accept()
                    self.log("CONNECTION", f"New connection from {address[0]}:{address[1]}")
                    
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except Exception as e:
                    self.log("ERROR", f"Accept error: {e}")
                    
        except Exception as e:
            self.log("ERROR", f"Server startup failed: {e}")
            traceback.print_exc()
        finally:
            self.server_socket.close()


def main():
    console = Console()
    try:
        server = ChatServer()
        server.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server shutting down...[/yellow]")
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        traceback.print_exc()


if __name__ == '__main__':
    main()