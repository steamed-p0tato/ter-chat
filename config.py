"""
Configuration file for Mystiko Chat
"""

# Server settings
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000
DEFAULT_SERVER = 'localhost'
DEFAULT_PORT = 5000
BUFFER_SIZE = 4096

# Room settings
MAX_ROOM_NAME_LENGTH = 30
MIN_ROOM_NAME_LENGTH = 3
MAX_ROOMS_PER_USER = 5
MAX_MESSAGE_LENGTH = 1000

# Chat history settings
CHAT_HISTORY_LIMIT = 50  # Number of messages to load when joining a room

# Database settings
DATABASE_PATH = 'mystiko.db'