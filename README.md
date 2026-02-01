# Mystiko Chat

```
███████╗ ██████╗ ██╗   ██╗███████╗████████╗██╗██╗  ██╗ ██████╗ 
██╔════╝██╔═══██╗╚██╗ ██╔╝██╔════╝╚══██╔══╝██║██║ ██╔╝██╔═══██╗
███████╗██║   ██║ ╚████╔╝ ███████╗   ██║   ██║█████╔╝ ██║   ██║
╚════██║██║   ██║  ╚██╔╝  ╚════██║   ██║   ██║██╔═██╗ ██║   ██║
███████║╚██████╔╝   ██║   ███████║   ██║   ██║██║  ██╗╚██████╔╝
╚══════╝ ╚═════╝    ╚═╝   ╚══════╝   ╚═╝   ╚═╝╚═╝  ╚═╝ ╚═════╝ 
```

**Anon • Fast • Dead-Simple**

A multi-room terminal-based chat application with persistent SQLite storage, built with Python and Textual.

## Features

- **Multi-Room Chat**: Join or create public chat rooms with descriptions
- **User Authentication**: Register and login with secure username/password
- **Chat History**: Last 50 messages per room loaded automatically
- **Real-Time Messaging**: Instant message delivery to all room members
- **Private Messages**: Send direct messages to other online users
- **Room Management**: Create rooms, view available rooms, delete your rooms
- **Beautiful Terminal UI**: Modern interface powered by Textual and Rich
- **Persistent Storage**: SQLite database for users, rooms, and messages
- **Thread-Safe**: Concurrent client connections with proper locking

## Screenshots

The application features a beautiful ASCII art logo and modern terminal interface with:
- Login/Register screens with tabbed interface
- Lobby screen showing available rooms with user counts
- Chat screen with message history, user list, and command support
- Modals for alerts and confirmations

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd ter-chat
```

2. Create a virtual environment (recommended):
```bash
python -m venv myenv
source myenv/bin/activate  # On Windows: myenv\Scripts\activate
```

3. Install dependencies:
```bash
pip install textual rich
```

4. The database will be created automatically on first run (`mystiko.db`)

## Usage

### Starting the Server

Run the server on the default port (5000):

```bash
python server.py
```

The server will display:
- ASCII art logo
- Server statistics (users, rooms)
- Real-time logs for all server events

Default server address: `0.0.0.0:5000`

### Running the Client

In a new terminal:

```bash
python client.py
```

### Authentication

**Login:**
- Enter your username and password
- Default users are pre-created:
  - `admin` / `admin123`
  - `alice` / `alice123`
  - `bob` / `bob123`
  - `charlie` / `charlie123`

**Register:**
- Choose a username (3-20 characters, alphanumeric only)
- Choose a password (4+ characters)
- Confirm password

### Room Commands

From the lobby:
- Press `r` or click "Refresh" to reload room list
- Press `c` or click "Create Room" to create a new room
- Press `Esc` or click "Logout" to disconnect

### Chat Commands

Once in a room:
- `/help` - Show all available commands
- `/users` - List users in the current room
- `/pm <user> <message>` - Send a private message
- `/clear` - Clear your chat display
- `/leave` - Leave the current room

## Project Structure

```
ter-chat/
├── server.py          # Chat server with threading
├── client.py          # Terminal client with Textual UI
├── database.py        # SQLite database manager
├── config.py          # Configuration settings
└── mystiko.db         # SQLite database (auto-created)
```

## Configuration

Edit `config.py` to customize:

- Server host and port
- Room name length limits
- Maximum rooms per user (default: 5)
- Message length limit (default: 1000)
- Chat history limit (default: 50 messages)

## Database Schema

### Users Table
- `id` (Primary Key)
- `username` (Unique, case-insensitive)
- `password`
- `created_at`

### Rooms Table
- `id` (Primary Key)
- `name` (Unique, case-insensitive)
- `creator` (Foreign Key to users)
- `password` (Optional - for private rooms)
- `description`
- `created_at`

### Messages Table
- `id` (Primary Key)
- `room_name` (Foreign Key to rooms)
- `username` (Message sender)
- `content` (Message text)
- `message_type` (message/system/private)
- `timestamp`

## Technical Details

- **Protocol**: JSON over TCP sockets
- **Threading**: Each client connection handled in separate thread
- **Message Buffering**: Proper handling of partial/buffered messages
- **Thread-Safety**: Database operations use thread-local connections
- **UI Framework**: Textual (async) for responsive terminal interface

## Roadmap

- [ ] Private password-protected rooms
- [ ] User avatars
- [ ] Emoji support
- [ ] File sharing
- [ ] Room moderators/admins
- [ ] Message editing/deletion
- [ ] Typing indicators
- [ ] Web client option

## License

This project is open source and available under the MIT License.

## Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

## Credits

Built with:
- [Textual](https://textual.textualize.io/) - Terminal UI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [SQLite](https://www.sqlite.org/) - Embedded database

---

**Mystiko Chat** - Simple, fast, and anonymous terminal chatting.
