"""
Shared constants for SQLite Cult application.
Centralizes all magic strings, choices, and configuration values.
"""

# SQL Commands that modify data (require write permission)
WRITE_SQL_COMMANDS = frozenset([
    'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE',
    'REPLACE', 'UPSERT'
])

# Column type choices for SQLite
COLUMN_TYPES = [
    ('INTEGER', 'INTEGER'),
    ('TEXT', 'TEXT'),
    ('REAL', 'REAL'),
    ('BLOB', 'BLOB'),
    ('NUMERIC', 'NUMERIC'),
    ('BOOLEAN', 'BOOLEAN'),
    ('DATE', 'DATE'),
    ('DATETIME', 'DATETIME'),
    ('TIMESTAMP', 'TIMESTAMP'),
]

# Column constraint choices
COLUMN_CONSTRAINTS = [
    ('', 'None'),
    ('NOT NULL', 'NOT NULL'),
    ('UNIQUE', 'UNIQUE'),
    ('PRIMARY KEY', 'PRIMARY KEY'),
    ('PRIMARY KEY AUTOINCREMENT', 'PRIMARY KEY AUTOINCREMENT'),
]

# Permission levels for database sharing
PERMISSION_LEVELS = [
    ('read', 'Read Only'),
    ('write', 'Read & Write'),
    ('admin', 'Full Access (Admin)'),
]

# Chart types for dashboards
CHART_TYPES = [
    ('bar', 'Bar Chart'),
    ('line', 'Line Chart'),
    ('pie', 'Pie Chart'),
    ('doughnut', 'Doughnut Chart'),
    ('polarArea', 'Polar Area Chart'),
    ('radar', 'Radar Chart'),
]

# Auto-refresh intervals (in seconds)
REFRESH_INTERVALS = [
    (0, 'No auto-refresh'),
    (30, '30 seconds'),
    (60, '1 minute'),
    (300, '5 minutes'),
    (600, '10 minutes'),
    (1800, '30 minutes'),
    (3600, '1 hour'),
]

# Database file extensions
DB_EXTENSIONS = ('.db',)

# Pagination defaults
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# API Key length
API_KEY_LENGTH = 32

# Error messages
class ErrorMessages:
    """Centralized error messages for consistency."""
    PERMISSION_DENIED = "Permission denied."
    DATABASE_NOT_FOUND = "Database not found."
    TABLE_NOT_FOUND = "Table not found."
    ROW_NOT_FOUND = "Row not found."
    USER_NOT_FOUND = "User not found."
    INVALID_INPUT = "Invalid input provided."
    NO_FILE_UPLOADED = "No file uploaded."
    UNSUPPORTED_FORMAT = "Unsupported file format. Use CSV."
    REQUIRED_FIELDS = "All required fields must be provided."
    OWNER_REQUIRED = "Only the database owner can perform this action."
    ADMIN_REQUIRED = "Only administrators can perform this action."
    WRITE_PERMISSION_REQUIRED = "Write permission required."
    API_DISABLED = "API access is disabled for this database."
    INVALID_API_KEY = "Invalid API Key."
    MISSING_API_KEY = "Missing API Key."


# Success messages
class SuccessMessages:
    """Centralized success messages for consistency."""
    DATABASE_CREATED = 'Database "{name}" created successfully.'
    DATABASE_DELETED = 'Database "{name}" deleted successfully.'
    TABLE_CREATED = 'Table "{name}" created successfully.'
    TABLE_DROPPED = 'Table "{name}" dropped successfully.'
    COLUMN_ADDED = 'Column "{name}" added successfully.'
    COLUMN_DROPPED = 'Column "{name}" dropped successfully.'
    COLUMN_MODIFIED = 'Column "{name}" modified successfully.'
    INDEX_CREATED = 'Index "{name}" created successfully.'
    INDEX_DROPPED = 'Index "{name}" dropped successfully.'
    ROW_INSERTED = "Row inserted successfully."
    ROW_UPDATED = "Row updated successfully."
    ROW_DELETED = "Row deleted successfully."
    PERMISSION_GRANTED = 'Permission granted to {username}.'
    PERMISSION_REVOKED = 'Permission revoked for {username}.'
    OWNERSHIP_TRANSFERRED = 'Ownership transferred to {username}.'
    OWNERSHIP_CLAIMED = 'You are now the owner of "{name}".'
    API_ENABLED = "API access enabled."
    API_DISABLED = "API access disabled."
    API_KEY_REGENERATED = "API Key regenerated."
    IMPORT_SUCCESS = "Successfully imported {count} rows."
