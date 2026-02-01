"""
SQLite Database Manager for Mystiko Chat
"""

import sqlite3
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import DATABASE_PATH, CHAT_HISTORY_LIMIT


class DatabaseManager:
    """Thread-safe SQLite database manager"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.local = threading.local()
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self.local, 'connection') or self.local.connection is None:
            self.local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.local.connection.row_factory = sqlite3.Row
        return self.local.connection
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
    
    def _init_database(self):
        """Initialize database tables"""
        with self.get_cursor() as cursor:
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Rooms table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    creator TEXT NOT NULL,
                    password TEXT,
                    description TEXT DEFAULT 'No description',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator) REFERENCES users(username)
                )
            ''')
            
            # Messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message_type TEXT DEFAULT 'message',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (room_name) REFERENCES rooms(name) ON DELETE CASCADE
                )
            ''')
            
            # Create indexes for faster queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_rooms_creator ON rooms(creator)')
            
            # Insert default users if table is empty
            cursor.execute('SELECT COUNT(*) FROM users')
            if cursor.fetchone()[0] == 0:
                default_users = [
                    ('admin', 'admin123'),
                    ('alice', 'alice123'),
                    ('bob', 'bob123'),
                    ('charlie', 'charlie123')
                ]
                cursor.executemany(
                    'INSERT INTO users (username, password) VALUES (?, ?)',
                    default_users
                )
            
            # Insert default rooms if table is empty
            cursor.execute('SELECT COUNT(*) FROM rooms')
            if cursor.fetchone()[0] == 0:
                default_rooms = [
                    ('General', 'admin', None, 'General chat for everyone'),
                    ('Random', 'admin', None, 'Random discussions'),
                    ('Tech', 'admin', None, 'Technology discussions'),
                ]
                cursor.executemany(
                    'INSERT INTO rooms (name, creator, password, description) VALUES (?, ?, ?, ?)',
                    default_rooms
                )
    
    # ==================== User Operations ====================
    
    def user_exists(self, username: str) -> bool:
        """Check if a user exists (case-insensitive)"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT 1 FROM users WHERE username = ? COLLATE NOCASE',
                (username,)
            )
            return cursor.fetchone() is not None
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username (case-insensitive)"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT * FROM users WHERE username = ? COLLATE NOCASE',
                (username,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def create_user(self, username: str, password: str) -> bool:
        """Create a new user"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    'INSERT INTO users (username, password) VALUES (?, ?)',
                    (username, password)
                )
            return True
        except sqlite3.IntegrityError:
            return False
    
    def verify_user(self, username: str, password: str) -> Optional[str]:
        """Verify user credentials, returns actual username if valid"""
        user = self.get_user(username)
        if user and user['password'] == password:
            return user['username']
        return None
    
    def get_user_count(self) -> int:
        """Get total number of registered users"""
        with self.get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM users')
            return cursor.fetchone()[0]
    
    # ==================== Room Operations ====================
    
    def room_exists(self, room_name: str) -> bool:
        """Check if a room exists (case-insensitive)"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT 1 FROM rooms WHERE name = ? COLLATE NOCASE',
                (room_name,)
            )
            return cursor.fetchone() is not None
    
    def get_room(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Get room by name (case-insensitive)"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT * FROM rooms WHERE name = ? COLLATE NOCASE',
                (room_name,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def create_room(self, name: str, creator: str, password: Optional[str] = None, 
                    description: str = 'No description') -> bool:
        """Create a new room"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    '''INSERT INTO rooms (name, creator, password, description) 
                       VALUES (?, ?, ?, ?)''',
                    (name, creator, password, description)
                )
            return True
        except sqlite3.IntegrityError:
            return False
    
    def delete_room(self, room_name: str) -> bool:
        """Delete a room and all its messages"""
        with self.get_cursor() as cursor:
            # Delete messages first
            cursor.execute('DELETE FROM messages WHERE room_name = ? COLLATE NOCASE', (room_name,))
            # Delete room
            cursor.execute('DELETE FROM rooms WHERE name = ? COLLATE NOCASE', (room_name,))
            return cursor.rowcount > 0
    
    def get_all_rooms(self, search: str = '') -> List[Dict[str, Any]]:
        """Get all rooms, optionally filtered by search"""
        with self.get_cursor() as cursor:
            if search:
                cursor.execute(
                    '''SELECT * FROM rooms WHERE name LIKE ? COLLATE NOCASE 
                       ORDER BY name''',
                    (f'%{search}%',)
                )
            else:
                cursor.execute('SELECT * FROM rooms ORDER BY name')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_rooms_by_creator(self, creator: str) -> List[Dict[str, Any]]:
        """Get all rooms created by a user"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT * FROM rooms WHERE creator = ? COLLATE NOCASE ORDER BY created_at DESC',
                (creator,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_room_count(self) -> int:
        """Get total number of rooms"""
        with self.get_cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM rooms')
            return cursor.fetchone()[0]
    
    def count_user_rooms(self, username: str) -> int:
        """Count rooms created by a user"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM rooms WHERE creator = ? COLLATE NOCASE',
                (username,)
            )
            return cursor.fetchone()[0]
    
    # ==================== Message Operations ====================
    
    def save_message(self, room_name: str, username: str, content: str, 
                     message_type: str = 'message') -> bool:
        """Save a message to the database"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    '''INSERT INTO messages (room_name, username, content, message_type, timestamp) 
                       VALUES (?, ?, ?, ?, ?)''',
                    (room_name, username, content, message_type, 
                     datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
            return True
        except Exception:
            return False
    
    def get_room_messages(self, room_name: str, limit: int = CHAT_HISTORY_LIMIT) -> List[Dict[str, Any]]:
        """Get recent messages from a room"""
        with self.get_cursor() as cursor:
            cursor.execute(
                '''SELECT * FROM messages 
                   WHERE room_name = ? COLLATE NOCASE 
                   ORDER BY timestamp DESC, id DESC 
                   LIMIT ?''',
                (room_name, limit)
            )
            # Reverse to get chronological order
            messages = [dict(row) for row in cursor.fetchall()]
            return list(reversed(messages))
    
    def get_message_count(self, room_name: str) -> int:
        """Get message count for a room"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT COUNT(*) FROM messages WHERE room_name = ? COLLATE NOCASE',
                (room_name,)
            )
            return cursor.fetchone()[0]
    
    def clear_room_messages(self, room_name: str) -> bool:
        """Clear all messages in a room"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'DELETE FROM messages WHERE room_name = ? COLLATE NOCASE',
                (room_name,)
            )
            return True


# Global database instance
db = DatabaseManager()