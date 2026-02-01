"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                           MYSTIKO CHAT CLIENT                                  ║
║                     Terminal Chat Application                                  ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import socket
import threading
import json
import asyncio
import time
from datetime import datetime
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Header, Footer, Static, Button, Input, Label,
    ListView, ListItem, DataTable,
    LoadingIndicator, TabbedContent, TabPane, RichLog
)
from rich.text import Text

from config import DEFAULT_SERVER, DEFAULT_PORT, BUFFER_SIZE


# ═══════════════════════════════════════════════════════════════════════════════
# ASCII ART
# ═══════════════════════════════════════════════════════════════════════════════

LOGO = """[bold cyan]
    ███╗   ███╗██╗   ██╗███████╗████████╗██╗██╗  ██╗ ██████╗ 
    ████╗ ████║╚██╗ ██╔╝██╔════╝╚══██╔══╝██║██║ ██╔╝██╔═══██╗
    ██╔████╔██║ ╚████╔╝ ███████╗   ██║   ██║█████╔╝ ██║   ██║
    ██║╚██╔╝██║  ╚██╔╝  ╚════██║   ██║   ██║██╔═██╗ ██║   ██║
    ██║ ╚═╝ ██║   ██║   ███████║   ██║   ██║██║  ██╗╚██████╔╝
    ╚═╝     ╚═╝   ╚═╝   ╚══════╝   ╚═╝   ╚═╝╚═╝  ╚═╝ ╚═════╝ 
[/]"""


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class StatusBar(Static):
    """Status bar showing connection info"""
    
    def __init__(self, username: str = "", room: str = "", connected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._username = username
        self._room = room
        self._connected = connected
    
    def set_info(self, username: str = "", room: str = "", connected: bool = False):
        self._username = username
        self._room = room
        self._connected = connected
        self.refresh()
    
    def render(self) -> str:
        time_str = datetime.now().strftime("%H:%M")
        
        if self._connected:
            status = "[green]● ONLINE[/]"
        else:
            status = "[red]● OFFLINE[/]"
        
        parts = [status]
        
        if self._username:
            parts.append(f"[cyan]User:[/] {self._username}")
        
        if self._room:
            parts.append(f"[magenta]Room:[/] {self._room}")
        
        parts.append(f"[dim]{time_str}[/]")
        
        return "  │  ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# MODALS
# ═══════════════════════════════════════════════════════════════════════════════

class AlertModal(ModalScreen):
    """Alert modal dialog"""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
    ]
    
    def __init__(self, message: str, alert_type: str = "info", title: str = "") -> None:
        super().__init__()
        self.alert_message = message
        self.alert_type = alert_type
        self.alert_title = title or alert_type.capitalize()
    
    def compose(self) -> ComposeResult:
        icon = {"success": "✓", "error": "✗", "warning": "⚠", "info": "ℹ"}.get(self.alert_type, "ℹ")
        color = {"success": "green", "error": "red", "warning": "yellow", "info": "cyan"}.get(self.alert_type, "cyan")
        
        with Container(id="alert-box"):
            yield Static(f"""[{color}]╔══════════════════════════════════════════════╗
║  [{icon}] {self.alert_title.upper():^40} ║
╠══════════════════════════════════════════════╣
║                                              ║
║  {self.alert_message:^42}  ║
║                                              ║
╚══════════════════════════════════════════════╝[/]""")
            yield Button("  OK  ", variant="primary", id="alert-ok")
    
    def action_close(self) -> None:
        self.dismiss()
    
    @on(Button.Pressed, "#alert-ok")
    def on_ok(self) -> None:
        self.dismiss()


class ConfirmModal(ModalScreen[bool]):
    """Confirmation modal"""
    
    BINDINGS = [
        Binding("escape", "no", "No"),
        Binding("y", "yes", "Yes"),
        Binding("n", "no", "No"),
    ]
    
    def __init__(self, message: str, title: str = "Confirm") -> None:
        super().__init__()
        self.confirm_message = message
        self.confirm_title = title
    
    def compose(self) -> ComposeResult:
        with Container(id="confirm-box"):
            yield Static(f"""[yellow]╔══════════════════════════════════════════════╗
║  [?] {self.confirm_title.upper():^40} ║
╠══════════════════════════════════════════════╣
║                                              ║
║  {self.confirm_message:^42}  ║
║                                              ║
╚══════════════════════════════════════════════╝[/]""")
            with Horizontal(id="confirm-buttons"):
                yield Button("  No  ", variant="error", id="confirm-no")
                yield Button("  Yes  ", variant="success", id="confirm-yes")
    
    def action_no(self) -> None:
        self.dismiss(False)
    
    def action_yes(self) -> None:
        self.dismiss(True)
    
    @on(Button.Pressed, "#confirm-no")
    def on_no(self) -> None:
        self.dismiss(False)
    
    @on(Button.Pressed, "#confirm-yes")
    def on_yes(self) -> None:
        self.dismiss(True)


# ═══════════════════════════════════════════════════════════════════════════════
# SCREENS
# ═══════════════════════════════════════════════════════════════════════════════

class LoginScreen(Screen):
    """Login screen with ASCII art"""
    
    BINDINGS = [Binding("escape", "quit", "Quit")]
    
    def compose(self) -> ComposeResult:
        with Container(id="login-container"):
            yield Static(LOGO, id="logo")
            
            yield Static(
                "[dim]════════════════════════════════════════════════════════════════[/]\n"
                "[bold white]   Anon  •  Fast  •  ded-Simple[/]\n"
                "[dim]════════════════════════════════════════════════════════════════[/]",
                id="tagline"
            )
            
            with TabbedContent(id="auth-tabs"):
                with TabPane("Login", id="login-tab"):
                    yield Static("""[cyan]┌─────────────────────────────────────────────┐
│              LOGIN                          │
└─────────────────────────────────────────────┘[/]""")
                    yield Label("Username:")
                    yield Input(placeholder="Enter username", id="login-username")
                    yield Label("Password:")
                    yield Input(placeholder="Enter password", password=True, id="login-password")
                    yield Label("Server:")
                    with Horizontal(id="login-server"):
                        yield Input(placeholder="Host", value=DEFAULT_SERVER, id="login-host")
                        yield Input(placeholder="Port", value=str(DEFAULT_PORT), id="login-port")
                    yield Static("", id="login-error")
                    yield Button("  LOGIN  ", variant="primary", id="login-btn")
                
                with TabPane("Register", id="register-tab"):
                    yield Static("""[green]┌─────────────────────────────────────────────┐
│            REGISTER                         │
└─────────────────────────────────────────────┘[/]""")
                    yield Label("Username: [dim](min 3 chars)[/]")
                    yield Input(placeholder="Choose username", id="register-username")
                    yield Label("Password: [dim](min 4 chars)[/]")
                    yield Input(placeholder="Choose password", password=True, id="register-password")
                    yield Label("Confirm Password:")
                    yield Input(placeholder="Confirm password", password=True, id="register-confirm")
                    yield Label("Server:")
                    with Horizontal(id="register-server"):
                        yield Input(placeholder="Host", value=DEFAULT_SERVER, id="register-host")
                        yield Input(placeholder="Port", value=str(DEFAULT_PORT), id="register-port")
                    yield Static("", id="register-error")
                    yield Button("  REGISTER  ", variant="success", id="register-btn")
            
            yield Button("  EXIT  ", variant="error", id="exit-btn")
    
    def on_mount(self) -> None:
        self.query_one("#login-username", Input).focus()
    
    @on(Button.Pressed, "#login-btn")
    def on_login(self) -> None:
        self.do_login()
    
    @on(Button.Pressed, "#register-btn")
    def on_register(self) -> None:
        self.do_register()
    
    @on(Button.Pressed, "#exit-btn")
    def on_exit(self) -> None:
        self.app.exit()
    
    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id and "login" in event.input.id:
            self.do_login()
        elif event.input.id and "register" in event.input.id:
            self.do_register()
    
    @work(exclusive=True)
    async def do_login(self) -> None:
        username = self.query_one("#login-username", Input).value.strip()
        password = self.query_one("#login-password", Input).value
        host = self.query_one("#login-host", Input).value.strip()
        port_str = self.query_one("#login-port", Input).value.strip()
        error = self.query_one("#login-error", Static)
        
        if not username or not password:
            error.update("[red]Username and password required[/]")
            return
        
        try:
            port = int(port_str)
        except ValueError:
            error.update("[red]Invalid port number[/]")
            return
        
        error.update("[cyan]Connecting...[/]")
        
        success, message = await self.app.do_auth(host, port, username, password, "login")
        
        if success:
            error.update(f"[green]{message}[/]")
            await asyncio.sleep(0.5)
            self.app.switch_screen(LobbyScreen())
        else:
            error.update(f"[red]{message}[/]")
    
    @work(exclusive=True)
    async def do_register(self) -> None:
        username = self.query_one("#register-username", Input).value.strip()
        password = self.query_one("#register-password", Input).value
        confirm = self.query_one("#register-confirm", Input).value
        host = self.query_one("#register-host", Input).value.strip()
        port_str = self.query_one("#register-port", Input).value.strip()
        error = self.query_one("#register-error", Static)
        
        if not username or not password or not confirm:
            error.update("[red]All fields required[/]")
            return
        
        if password != confirm:
            error.update("[red]Passwords don't match[/]")
            return
        
        if len(username) < 3:
            error.update("[red]Username too short[/]")
            return
        
        if len(password) < 4:
            error.update("[red]Password too short[/]")
            return
        
        try:
            port = int(port_str)
        except ValueError:
            error.update("[red]Invalid port number[/]")
            return
        
        error.update("[cyan]Creating account...[/]")
        
        success, message = await self.app.do_auth(host, port, username, password, "register")
        
        if success:
            error.update(f"[green]{message}[/]")
            await asyncio.sleep(0.5)
            self.app.switch_screen(LobbyScreen())
        else:
            error.update(f"[red]{message}[/]")


class LobbyScreen(Screen):
    """Lobby screen"""
    
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("c", "create_room", "Create"),
        Binding("escape", "logout", "Logout"),
    ]
    
    def __init__(self):
        super().__init__()
        self.rooms_data = []
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="lobby-container"):
            yield Static("""[bold cyan]╔═══════════════════════════════════════════════════════════════════════╗
║                              LOBBY                                    ║
╚═══════════════════════════════════════════════════════════════════════╝[/]""", id="lobby-header")
            
            yield StatusBar(id="lobby-status")
            
            with Horizontal(id="menu-buttons"):
                yield Button(" Refresh ", variant="default", id="refresh-btn")
                yield Button(" Create Room ", variant="success", id="create-btn")
                yield Button(" My Rooms ", variant="warning", id="myrooms-btn")
                yield Button(" Logout ", variant="error", id="logout-btn")
            
            yield Static("""[yellow]┌─────────────────────────────────────────────────────────────────────────┐
│                        AVAILABLE ROOMS                                  │
└─────────────────────────────────────────────────────────────────────────┘[/]""", id="rooms-header")
            
            yield LoadingIndicator(id="loading")
            yield DataTable(id="rooms-table", zebra_stripes=True)
        
        yield Footer()
    
    def on_mount(self) -> None:
        status = self.query_one("#lobby-status", StatusBar)
        status.set_info(username=self.app.username or "", connected=True)
        
        table = self.query_one("#rooms-table", DataTable)
        table.add_columns("#", "Room Name", "Type", "Users", "Creator", "Description")
        table.cursor_type = "row"
        
        self.load_rooms()
    
    @work(exclusive=True)
    async def load_rooms(self) -> None:
        loading = self.query_one("#loading", LoadingIndicator)
        table = self.query_one("#rooms-table", DataTable)
        
        loading.display = True
        table.display = False
        
        response = await self.app.send_and_receive({'type': 'list_rooms', 'search': ''})
        
        loading.display = False
        table.display = True
        
        if response and response.get('type') == 'room_list':
            self.rooms_data = response.get('rooms', [])
            self.update_table()
    
    def update_table(self) -> None:
        table = self.query_one("#rooms-table", DataTable)
        table.clear()
        
        for i, room in enumerate(self.rooms_data, 1):
            is_private = room.get('is_private', False)
            room_type = "🔒 Private" if is_private else "🌐 Public"
            type_style = "red" if is_private else "green"
            
            desc = room.get('description', 'No description') or 'No description'
            if len(desc) > 25:
                desc = desc[:22] + "..."
            
            table.add_row(
                str(i),
                room.get('name', 'Unknown'),
                Text(room_type, style=type_style),
                str(room.get('user_count', 0)),
                room.get('creator', 'Unknown'),
                desc,
                key=room.get('name', f'room_{i}')
            )
    
    @on(Button.Pressed, "#refresh-btn")
    def on_refresh(self) -> None:
        self.load_rooms()
    
    def action_refresh(self) -> None:
        self.load_rooms()
    
    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        
        room_name = str(event.row_key.value)
        room = next((r for r in self.rooms_data if r.get('name') == room_name), None)
        
        if room:
            self.try_join_room(room)
    
    @work(exclusive=True)
    async def try_join_room(self, room: dict) -> None:
        # Private rooms are disabled for now
        if room.get('is_private'):
            self.app.push_screen(AlertModal("🔒 Private rooms coming soon!", 'info', 'Coming Soon'))
            return
        
        response = await self.app.send_and_receive({
            'type': 'join_room',
            'room_name': room['name'],
            'password': None
        })
        
        if response:
            if response.get('type') == 'room_joined':
                self.app.current_room = response.get('room_name')
                self.app.push_screen(ChatScreen())
            elif response.get('type') == 'error':
                self.app.push_screen(AlertModal(response.get('message', 'Error'), 'error'))
    
    @on(Button.Pressed, "#create-btn")
    def on_create(self) -> None:
        self.app.push_screen(CreateRoomScreen())
    
    def action_create_room(self) -> None:
        self.app.push_screen(CreateRoomScreen())
    
    @on(Button.Pressed, "#myrooms-btn")
    def on_my_rooms(self) -> None:
        self.app.push_screen(MyRoomsScreen())
    
    @on(Button.Pressed, "#logout-btn")
    def on_logout_btn(self) -> None:
        self.do_logout()
    
    @work(exclusive=True)
    async def do_logout(self) -> None:
        result = await self.app.push_screen_wait(ConfirmModal("Logout?", "Confirm"))
        if result:
            self.app.disconnect()
            self.app.switch_screen(LoginScreen())
    
    def action_logout(self) -> None:
        self.do_logout()


class CreateRoomScreen(Screen):
    """Create room screen - Private rooms disabled"""
    
    BINDINGS = [Binding("escape", "go_back", "Back")]
    
    def compose(self) -> ComposeResult:
        with Container(id="create-container"):
            yield Static("""[bold green]╔═══════════════════════════════════════════════════════════╗
║                    CREATE NEW ROOM                        ║
╚═══════════════════════════════════════════════════════════╝[/]""", id="create-header")
            
            yield Label("Room Name: [dim](min 3 characters)[/]")
            yield Input(placeholder="Enter room name", id="room-name")
            
            yield Label("Description: [dim](optional)[/]")
            yield Input(placeholder="Enter description", id="room-desc")
            
            # Private rooms coming soon notice
            yield Static("""
[dim yellow]┌─────────────────────────────────────────────────────────────┐
│  🔒 Private Rooms - COMING SOON!                           │
│                                                             │
│  Password-protected rooms will be available in a future    │
│  update. Stay tuned!                                        │
└─────────────────────────────────────────────────────────────┘[/]""", id="private-notice")
            
            yield Static("", id="create-result")
            
            with Horizontal(id="create-buttons"):
                yield Button(" Cancel ", variant="error", id="cancel-btn")
                yield Button(" Create Public Room ", variant="success", id="create-btn")
    
    def on_mount(self) -> None:
        self.query_one("#room-name", Input).focus()
    
    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self) -> None:
        self.app.pop_screen()
    
    def action_go_back(self) -> None:
        self.app.pop_screen()
    
    @on(Button.Pressed, "#create-btn")
    def on_create_pressed(self) -> None:
        self.create_room()
    
    @on(Input.Submitted)
    def on_input_submit(self, event: Input.Submitted) -> None:
        self.create_room()
    
    @work(exclusive=True)
    async def create_room(self) -> None:
        room_name = self.query_one("#room-name", Input).value.strip()
        description = self.query_one("#room-desc", Input).value.strip()
        result = self.query_one("#create-result", Static)
        btn = self.query_one("#create-btn", Button)
        
        if len(room_name) < 3:
            result.update("[red]Room name must be at least 3 characters[/]")
            return
        
        result.update("[cyan]Creating room...[/]")
        btn.disabled = True
        
        try:
            response = await self.app.send_and_receive({
                'type': 'create_room',
                'room_name': room_name,
                'description': description or 'No description',
                'password': None  # Always public for now
            })
            
            if response:
                if response.get('type') == 'room_created':
                    result.update(f"[green]{response.get('message', 'Created!')}[/]")
                    await asyncio.sleep(1)
                    self.app.pop_screen()
                else:
                    result.update(f"[red]{response.get('message', 'Error')}[/]")
            else:
                result.update("[red]No response from server[/]")
        finally:
            btn.disabled = False


class MyRoomsScreen(Screen):
    """My rooms screen"""
    
    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]
    
    def __init__(self):
        super().__init__()
        self.my_rooms_data = []
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="myrooms-container"):
            yield Static("""[bold yellow]╔═══════════════════════════════════════════════════════════════════════╗
║                          MY ROOMS                                     ║
║                   (Click on a room to delete)                         ║
╚═══════════════════════════════════════════════════════════════════════╝[/]""", id="myrooms-header")
            
            yield LoadingIndicator(id="myrooms-loading")
            yield DataTable(id="myrooms-table", zebra_stripes=True)
            
            with Horizontal(id="myrooms-buttons"):
                yield Button(" Back ", variant="default", id="back-btn")
                yield Button(" Refresh ", variant="primary", id="refresh-btn")
        
        yield Footer()
    
    def on_mount(self) -> None:
        table = self.query_one("#myrooms-table", DataTable)
        table.add_columns("#", "Room Name", "Type", "Users", "Created")
        table.cursor_type = "row"
        self.load_my_rooms()
    
    @work(exclusive=True)
    async def load_my_rooms(self) -> None:
        loading = self.query_one("#myrooms-loading", LoadingIndicator)
        table = self.query_one("#myrooms-table", DataTable)
        
        loading.display = True
        table.display = False
        
        response = await self.app.send_and_receive({'type': 'get_my_rooms'})
        
        loading.display = False
        table.display = True
        
        if response and response.get('type') == 'my_rooms':
            self.my_rooms_data = response.get('rooms', [])
            self.update_table()
    
    def update_table(self) -> None:
        table = self.query_one("#myrooms-table", DataTable)
        table.clear()
        
        for i, room in enumerate(self.my_rooms_data, 1):
            is_private = room.get('is_private', False)
            room_type = "🔒 Private" if is_private else "🌐 Public"
            type_style = "red" if is_private else "green"
            
            table.add_row(
                str(i),
                room.get('name', 'Unknown'),
                Text(room_type, style=type_style),
                str(room.get('user_count', 0)),
                room.get('created_at', 'Unknown'),
                key=room.get('name', f'room_{i}')
            )
    
    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        
        room_name = str(event.row_key.value)
        room = next((r for r in self.my_rooms_data if r.get('name') == room_name), None)
        
        if room:
            self.delete_room(room)
    
    @work(exclusive=True)
    async def delete_room(self, room: dict) -> None:
        message = f"Delete '{room['name']}'?"
        if room.get('user_count', 0) > 0:
            message = f"Delete '{room['name']}'? ({room['user_count']} users will be kicked)"
        
        result = await self.app.push_screen_wait(ConfirmModal(message, "Delete Room"))
        
        if result:
            response = await self.app.send_and_receive({
                'type': 'delete_room',
                'room_name': room['name']
            })
            
            if response and response.get('type') == 'room_delete_success':
                self.notify("Room deleted")
                self.load_my_rooms()
    
    @on(Button.Pressed, "#back-btn")
    def on_back(self) -> None:
        self.app.pop_screen()
    
    def action_go_back(self) -> None:
        self.app.pop_screen()
    
    @on(Button.Pressed, "#refresh-btn")
    def on_refresh(self) -> None:
        self.load_my_rooms()
    
    def action_refresh(self) -> None:
        self.load_my_rooms()


class ChatScreen(Screen):
    """Chat screen with persistent history"""
    
    BINDINGS = [
        Binding("escape", "leave_room", "Leave"),
        Binding("ctrl+l", "clear_chat", "Clear"),
    ]
    
    def __init__(self):
        super().__init__()
        self.room_users_list = []
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Horizontal(id="chat-layout"):
            with Vertical(id="chat-main"):
                yield Static(f"""[bold cyan]╔═══════════════════════════════════════════════════════════════════════╗
║  ROOM: {self.app.current_room or 'Unknown':<64} ║
╚═══════════════════════════════════════════════════════════════════════╝[/]""", id="room-header")
                
                yield RichLog(id="chat-log", highlight=True, markup=True)
                
                yield Static("[dim]─────────────────────────────────────────────────────────────────────────────[/]\n"
                           "[dim]Commands:[/] /help | /pm user msg | /users | /clear | /leave", id="help-hint")
                
                with Horizontal(id="input-row"):
                    yield Input(placeholder="Type message...", id="message-input")
                    yield Button("Send", variant="primary", id="send-btn")
            
            with Vertical(id="users-sidebar"):
                yield Static("""[green]┌──────────────────────┐
│    USERS ONLINE      │
├──────────────────────┤[/]""", id="users-header")
                yield ListView(id="users-list")
                yield Static("[green]└──────────────────────┘[/]", id="users-footer")
        
        yield Footer()
    
    def on_mount(self) -> None:
        self.query_one("#message-input", Input).focus()
        
        self.add_system_message("Loading chat history...")
        
        if self.app.current_room:
            self.app.send_data({'type': 'get_room_users', 'room_name': self.app.current_room})
        
        self.app.start_chat_receiver(self)
    
    def on_unmount(self) -> None:
        self.app.stop_chat_receiver()
    
    def load_chat_history(self, messages: list) -> None:
        """Load chat history from server"""
        try:
            chat_log = self.query_one("#chat-log", RichLog)
            chat_log.clear()
            
            if messages:
                chat_log.write(f"[dim]─── Chat History ({len(messages)} messages) ───[/]")
                
                for msg in messages:
                    msg_type = msg.get('message_type', 'message')
                    username = msg.get('username', 'Unknown')
                    content = msg.get('content', '')
                    timestamp = msg.get('timestamp', '')
                    
                    # Format timestamp
                    if timestamp:
                        try:
                            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                            time_str = dt.strftime('%H:%M')
                        except:
                            time_str = timestamp[-8:-3] if len(timestamp) > 8 else timestamp
                    else:
                        time_str = ""
                    
                    if msg_type == 'system':
                        chat_log.write(f"[yellow]*** {content} ***[/]")
                    else:
                        if username.lower() == self.app.username.lower() if self.app.username else False:
                            chat_log.write(f"[cyan][{time_str}] You:[/] {content}")
                        else:
                            chat_log.write(f"[green][{time_str}] {username}:[/] {content}")
                
                chat_log.write(f"[dim]─── End of History ───[/]\n")
            else:
                chat_log.write("[dim]No previous messages in this room.[/]\n")
            
            self.add_system_message("Welcome to the room! Type /help for commands.")
        except Exception as e:
            pass
    
    def add_message(self, msg_type: str, content: str, username: str = "", is_self: bool = False) -> None:
        try:
            chat_log = self.query_one("#chat-log", RichLog)
            timestamp = datetime.now().strftime("%H:%M")
            
            if msg_type == "message":
                if is_self:
                    chat_log.write(f"[cyan][{timestamp}] You:[/] {content}")
                else:
                    chat_log.write(f"[green][{timestamp}] {username}:[/] {content}")
            elif msg_type == "system":
                chat_log.write(f"[yellow]*** {content} ***[/]")
            elif msg_type == "private_received":
                chat_log.write(f"[magenta][{timestamp}] (PM from {username}):[/] {content}")
            elif msg_type == "private_sent":
                chat_log.write(f"[blue][{timestamp}] (PM to {username}):[/] {content}")
            elif msg_type == "error":
                chat_log.write(f"[red]Error: {content}[/]")
        except:
            pass
    
    def add_system_message(self, message: str) -> None:
        self.add_message("system", message)
    
    def update_users(self, users: list) -> None:
        try:
            self.room_users_list = users
            users_list = self.query_one("#users-list", ListView)
            users_list.clear()
            
            for user in users:
                if user == self.app.username:
                    users_list.append(ListItem(Label(f"[cyan]│ {user} (you)[/]")))
                else:
                    users_list.append(ListItem(Label(f"[green]│ {user}[/]")))
        except:
            pass
    
    @on(Button.Pressed, "#send-btn")
    def on_send_btn(self) -> None:
        msg_input = self.query_one("#message-input", Input)
        message = msg_input.value.strip()
        msg_input.value = ""
        
        if message:
            if message.startswith('/'):
                self.handle_command(message)
            else:
                self.app.send_data({'type': 'message', 'content': message})
        
        msg_input.focus()
    
    @on(Input.Submitted, "#message-input")
    def on_message_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        event.input.value = ""
        
        if not message:
            return
        
        if message.startswith('/'):
            self.handle_command(message)
        else:
            self.app.send_data({'type': 'message', 'content': message})
    
    def handle_command(self, command: str) -> None:
        parts = command.split(maxsplit=2)
        cmd = parts[0].lower()
        
        if cmd in ['/leave', '/exit', '/quit']:
            self.action_leave_room()
        elif cmd in ['/users', '/who']:
            if self.app.current_room:
                self.app.send_data({'type': 'get_room_users', 'room_name': self.app.current_room})
        elif cmd in ['/clear', '/cls']:
            self.action_clear_chat()
        elif cmd in ['/help', '/?']:
            self.show_help()
        elif cmd in ['/pm', '/msg', '/w']:
            if len(parts) >= 3:
                target = parts[1]
                msg = parts[2]
                if self.app.username and target.lower() == self.app.username.lower():
                    self.add_message("error", "Cannot message yourself")
                else:
                    self.app.send_data({'type': 'private', 'target': target, 'content': msg})
            else:
                self.add_message("error", "Usage: /pm <user> <message>")
        else:
            self.add_message("error", f"Unknown command: {cmd}")
    
    def show_help(self) -> None:
        try:
            chat_log = self.query_one("#chat-log", RichLog)
            chat_log.write("""
[cyan]╔════════════════════════════════════════════════════════════╗
║                       COMMANDS                             ║
╠════════════════════════════════════════════════════════════╣
║  /help          - Show this help                           ║
║  /users         - List users in room                       ║
║  /pm user msg   - Send private message                     ║
║  /clear         - Clear chat display                       ║
║  /leave         - Leave room                               ║
╚════════════════════════════════════════════════════════════╝[/]
""")
        except:
            pass
    
    def action_leave_room(self) -> None:
        self.app.send_data({'type': 'leave_room'})
        self.app.current_room = None
        self.app.pop_screen()
    
    def action_clear_chat(self) -> None:
        try:
            self.query_one("#chat-log", RichLog).clear()
            self.add_system_message("Chat cleared (history still saved on server)")
        except:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════

class ChatApp(App):
    """Chat Application"""
    
    CSS = """
    /* Login Screen */
    LoginScreen {
        align: center middle;
    }
    
    #login-container {
        width: 75;
        height: auto;
        padding: 1 2;
        border: double cyan;
        background: $surface;
    }
    
    #logo {
        text-align: center;
    }
    
    #tagline {
        text-align: center;
        margin: 1 0;
    }
    
    #auth-tabs {
        height: auto;
        margin: 1 0;
    }
    
    #login-server, #register-server {
        height: 3;
        margin: 1 0;
    }
    
    #login-server Input, #register-server Input {
        margin-right: 1;
    }
    
    #login-error, #register-error {
        height: 2;
        text-align: center;
        margin: 1 0;
    }
    
    #login-btn, #register-btn {
        width: 100%;
        margin-top: 1;
    }
    
    #exit-btn {
        width: 100%;
        margin-top: 1;
    }
    
    /* Lobby Screen */
    #lobby-container {
        padding: 1 2;
    }
    
    #lobby-header {
        margin-bottom: 1;
    }
    
    #lobby-status {
        margin: 1 0;
    }
    
    #menu-buttons {
        height: 3;
        margin: 1 0;
    }
    
    #menu-buttons Button {
        margin-right: 1;
    }
    
    #rooms-header {
        margin: 1 0;
    }
    
    #rooms-table {
        height: 100%;
    }
    
    LoadingIndicator {
        height: 3;
    }
    
    /* Create Room Screen */
    CreateRoomScreen {
        align: center middle;
    }
    
    #create-container {
        width: 70;
        height: auto;
        padding: 1 2;
        border: double green;
        background: $surface;
    }
    
    #create-header {
        margin-bottom: 1;
    }
    
    #private-notice {
        margin: 1 0;
    }
    
    #create-result {
        height: 2;
        text-align: center;
        margin: 1 0;
    }
    
    #create-buttons {
        height: 3;
        margin-top: 1;
        align: center middle;
    }
    
    #create-buttons Button {
        margin: 0 1;
    }
    
    /* My Rooms Screen */
    #myrooms-container {
        padding: 2;
    }
    
    #myrooms-header {
        margin-bottom: 1;
    }
    
    #myrooms-table {
        height: 100%;
        margin-bottom: 1;
    }
    
    #myrooms-buttons {
        dock: bottom;
        height: 3;
    }
    
    #myrooms-buttons Button {
        margin-right: 1;
    }
    
    /* Chat Screen */
    #chat-layout {
        height: 100%;
    }
    
    #chat-main {
        width: 4fr;
        padding: 1;
    }
    
    #room-header {
        height: auto;
    }
    
    #chat-log {
        height: 1fr;
        border: solid $primary-darken-2;
        margin: 1 0;
        padding: 1;
    }
    
    #help-hint {
        height: auto;
        margin-bottom: 1;
    }
    
    #input-row {
        height: 3;
    }
    
    #message-input {
        width: 1fr;
    }
    
    #send-btn {
        width: 10;
        margin-left: 1;
    }
    
    #users-sidebar {
        width: 26;
        padding: 1;
    }
    
    #users-header {
        height: auto;
    }
    
    #users-list {
        height: 1fr;
    }
    
    #users-footer {
        height: auto;
    }
    
    /* Modals */
    ModalScreen {
        align: center middle;
    }
    
    #alert-box, #confirm-box {
        width: 52;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: double $primary;
    }
    
    #alert-ok {
        width: 100%;
        margin-top: 1;
    }
    
    #confirm-buttons {
        height: 3;
        margin-top: 1;
        align: center middle;
    }
    
    #confirm-buttons Button {
        margin: 0 1;
    }
    """
    
    TITLE = "Mystiko Chat"
    
    def __init__(self):
        super().__init__()
        self.socket: Optional[socket.socket] = None
        self.username: Optional[str] = None
        self.current_room: Optional[str] = None
        self.receive_buffer = ""
        self.buffer_lock = threading.Lock()
        self.chat_active = False
        self.receive_thread: Optional[threading.Thread] = None
        self.chat_screen: Optional[ChatScreen] = None
    
    def on_mount(self) -> None:
        self.push_screen(LoginScreen())
    
    def connect(self, host: str, port: int) -> tuple[bool, str]:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((host, port))
            self.socket.settimeout(None)
            self.receive_buffer = ""
            return True, "Connected"
        except socket.timeout:
            return False, "Connection timed out"
        except ConnectionRefusedError:
            return False, "Connection refused"
        except socket.gaierror:
            return False, "Invalid server address"
        except Exception as e:
            return False, f"Error: {e}"
    
    def disconnect(self) -> None:
        self.chat_active = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.username = None
        self.current_room = None
        self.receive_buffer = ""
    
    def send_data(self, data: dict) -> bool:
        try:
            if self.socket:
                self.socket.sendall((json.dumps(data) + '\n').encode())
                return True
        except:
            pass
        return False
    
    def receive_one_message(self, timeout: float = 10) -> Optional[dict]:
        try:
            if not self.socket:
                return None
            
            self.socket.settimeout(timeout)
            start = time.time()
            
            while time.time() - start < timeout:
                with self.buffer_lock:
                    if '\n' in self.receive_buffer:
                        line, self.receive_buffer = self.receive_buffer.split('\n', 1)
                        if line.strip():
                            try:
                                return json.loads(line.strip())
                            except:
                                continue
                
                try:
                    data = self.socket.recv(BUFFER_SIZE).decode()
                    if not data:
                        return None
                    with self.buffer_lock:
                        self.receive_buffer += data
                except socket.timeout:
                    continue
            return None
        except:
            return None
        finally:
            if self.socket:
                try:
                    self.socket.settimeout(None)
                except:
                    pass
    
    async def send_and_receive(self, data: dict, timeout: float = 10) -> Optional[dict]:
        loop = asyncio.get_event_loop()
        
        def _do():
            try:
                if not self.send_data(data):
                    return {'type': 'error', 'message': 'Send failed'}
                
                expected = {
                    'list_rooms': ['room_list'],
                    'create_room': ['room_created', 'error'],
                    'join_room': ['room_joined', 'error'],
                    'leave_room': ['room_left', 'error'],
                    'delete_room': ['room_delete_success', 'error'],
                    'get_my_rooms': ['my_rooms'],
                    'get_room_users': ['room_users'],
                }.get(data.get('type'), ['error'])
                
                start = time.time()
                while time.time() - start < timeout:
                    try:
                        if not self.socket:
                            return {'type': 'error', 'message': 'Disconnected'}
                        
                        self.socket.settimeout(1.0)
                        
                        with self.buffer_lock:
                            if '\n' in self.receive_buffer:
                                line, self.receive_buffer = self.receive_buffer.split('\n', 1)
                                if line.strip():
                                    try:
                                        resp = json.loads(line.strip())
                                        if resp.get('type') in expected or resp.get('type') == 'error':
                                            return resp
                                    except:
                                        pass
                        
                        try:
                            chunk = self.socket.recv(BUFFER_SIZE).decode()
                            if chunk:
                                with self.buffer_lock:
                                    self.receive_buffer += chunk
                        except socket.timeout:
                            pass
                    except socket.timeout:
                        continue
                    except Exception as e:
                        return {'type': 'error', 'message': str(e)}
                
                return {'type': 'error', 'message': 'Timeout'}
            except Exception as e:
                return {'type': 'error', 'message': str(e)}
            finally:
                if self.socket:
                    try:
                        self.socket.settimeout(None)
                    except:
                        pass
        
        return await loop.run_in_executor(None, _do)
    
    async def do_auth(self, host: str, port: int, username: str, password: str, action: str) -> tuple[bool, str]:
        loop = asyncio.get_event_loop()
        
        def _auth():
            ok, msg = self.connect(host, port)
            if not ok:
                return False, msg
            
            if not self.send_data({'action': action, 'username': username, 'password': password}):
                return False, "Send failed"
            
            resp = self.receive_one_message(timeout=15)
            if resp:
                if resp.get('status') == 'success':
                    self.username = username
                    return True, resp.get('message', 'OK')
                else:
                    self.disconnect()
                    return False, resp.get('message', 'Failed')
            
            self.disconnect()
            return False, "No response"
        
        return await loop.run_in_executor(None, _auth)
    
    def start_chat_receiver(self, screen: ChatScreen) -> None:
        self.chat_screen = screen
        self.chat_active = True
        self.receive_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.receive_thread.start()
    
    def stop_chat_receiver(self) -> None:
        self.chat_active = False
        self.chat_screen = None
    
    def _recv_loop(self) -> None:
        while self.chat_active and self.socket:
            try:
                self.socket.settimeout(0.5)
                data = self.socket.recv(BUFFER_SIZE).decode()
                self.socket.settimeout(None)
                
                if not data:
                    break
                
                with self.buffer_lock:
                    self.receive_buffer += data
                    while '\n' in self.receive_buffer:
                        line, self.receive_buffer = self.receive_buffer.split('\n', 1)
                        if line.strip():
                            try:
                                msg = json.loads(line.strip())
                                self.call_from_thread(self._handle_msg, msg)
                            except:
                                pass
            except socket.timeout:
                continue
            except:
                break
    
    def _handle_msg(self, msg: dict) -> None:
        if not self.chat_screen:
            return
        
        try:
            t = msg.get('type')
            
            if t == 'chat_history':
                # Load chat history
                messages = msg.get('messages', [])
                self.chat_screen.load_chat_history(messages)
            elif t == 'message':
                u = msg.get('username', '?')
                c = msg.get('message', '')
                is_self = self.username and u.lower() == self.username.lower()
                self.chat_screen.add_message("message", c, u, is_self)
            elif t == 'system':
                self.chat_screen.add_system_message(msg.get('message', ''))
            elif t == 'private':
                self.chat_screen.add_message("private_received", msg.get('message', ''), msg.get('from', '?'))
            elif t == 'private_sent':
                self.chat_screen.add_message("private_sent", msg.get('message', ''), msg.get('to', '?'))
            elif t == 'room_users':
                self.chat_screen.update_users(msg.get('users', []))
            elif t == 'room_deleted':
                self.current_room = None
                self.chat_active = False
                self.push_screen(AlertModal(msg.get('message', 'Room deleted'), 'warning'))
                self.pop_screen()
            elif t == 'error':
                self.chat_screen.add_message("error", msg.get('message', '?'))
        except:
            pass


def main():
    ChatApp().run()


if __name__ == '__main__':
    main()