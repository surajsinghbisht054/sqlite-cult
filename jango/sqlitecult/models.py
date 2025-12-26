import os
import sqlite3
import json
import csv
import io
import secrets
from pathlib import Path
from contextlib import contextmanager
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import PermissionDenied


class DatabasePermissionChecker:
    """
    Centralized permission checking for database operations.
    Handles the authorization logic for all database access.
    """
    
    @staticmethod
    def is_superuser_or_staff(user):
        """Check if user is a superuser or staff member."""
        return user.is_superuser or user.is_staff
    
    @staticmethod
    def can_access_database(user, database_name, require_write=False, require_admin=False):
        """
        Check if a user can access a database.
        
        Args:
            user: The user requesting access
            database_name: The name of the database
            require_write: If True, requires write permission (for modifying data)
            require_admin: If True, requires admin permission (for deleting database)
        
        Returns:
            tuple: (can_access: bool, reason: str)
        """
        # Import here to avoid circular imports
        from .models import DatabaseOwnership, DatabasePermission
        
        # Superusers and staff can access everything
        if user.is_superuser or user.is_staff:
            return True, "Admin access"
        
        # Check if user is the owner
        if DatabaseOwnership.is_owner(user, database_name):
            return True, "Owner access"
        
        # Check shared permissions
        perm_level = DatabasePermission.get_permission_level(user, database_name)
        
        if perm_level is None:
            return False, "No access permission"
        
        if require_admin:
            if perm_level == 'admin':
                return True, "Admin permission"
            return False, "Admin permission required"
        
        if require_write:
            if perm_level in ['write', 'admin']:
                return True, "Write permission"
            return False, "Write permission required"
        
        # Read access is enough
        return True, f"{perm_level.capitalize()} permission"
    
    @staticmethod
    def get_accessible_databases(user):
        """
        Get list of databases a user can access.
        
        Returns:
            list: List of database names the user can access
        """
        from .models import DatabaseOwnership, DatabasePermission
        
        # Superusers and staff can access all databases
        if user.is_superuser or user.is_staff:
            return SQLiteManager.list_databases(), True  # True indicates "all access"
        
        accessible = set()
        
        # Add owned databases
        owned = DatabaseOwnership.objects.filter(owner=user).values_list('database_name', flat=True)
        accessible.update(owned)
        
        # Add shared databases
        shared = DatabasePermission.objects.filter(granted_to=user).values_list('database_name', flat=True)
        accessible.update(shared)
        
        # Filter to only include databases that actually exist
        existing = set(SQLiteManager.list_databases())
        accessible = accessible.intersection(existing)
        
        return list(accessible), False  # False indicates "limited access"
    
    @staticmethod
    def check_database_name_available(user, database_name):
        """
        Check if a database name is available for a user to use.
        
        Returns:
            tuple: (is_available: bool, error_message: str or None)
        """
        from .models import DatabaseOwnership
        
        # Check if database file already exists
        db_path = SQLiteManager.get_database_path(database_name)
        if db_path.exists():
            # Check who owns it
            owner = DatabaseOwnership.get_owner(database_name)
            if owner:
                if owner == user:
                    return False, "You already own a database with this name."
                return False, f"This database name is already in use by another user."
            else:
                # Database file exists but no ownership record (legacy database)
                # Superusers can claim it
                if user.is_superuser or user.is_staff:
                    return True, None
                return False, "This database name is already in use."
        
        # Check ownership records (in case file was deleted but record exists)
        if DatabaseOwnership.database_name_exists(database_name):
            owner = DatabaseOwnership.get_owner(database_name)
            if owner and owner != user:
                return False, "This database name is reserved by another user."
        
        return True, None


class SQLiteManager:
    """
    Manager class for all SQLite database operations.
    Centralizes database logic for better maintainability.
    """
    
    @staticmethod
    def get_databases_folder():
        """Get or create the databases folder."""
        folder = Path(settings.SQLITE_DATABASES_FOLDER)
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    
    @staticmethod
    def get_database_path(db_name):
        """Get the full path to a database file."""
        if not db_name.endswith('.db') and not db_name.endswith('.sqlite') and not db_name.endswith('.sqlite3'):
            db_name = f"{db_name}.db"
        return SQLiteManager.get_databases_folder() / db_name
    
    @staticmethod
    @contextmanager
    def get_connection(db_name, row_factory=False):
        """
        Context manager for database connections.
        Ensures connections are properly closed to prevent database locks.
        """
        db_path = SQLiteManager.get_database_path(db_name)
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for better concurrency
        conn.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
        if row_factory:
            conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    @staticmethod
    def list_databases():
        """List all SQLite databases in the configured folder."""
        folder = SQLiteManager.get_databases_folder()
        extensions = ('.db', )
        databases = []
        for f in folder.iterdir():
            if f.is_file() and f.suffix in extensions:
                databases.append(f.name)

        return sorted(databases)
    
    @staticmethod
    def get_database_info(db_name):
        """Get information about a database."""
        db_path = SQLiteManager.get_database_path(db_name)
        try:
            tables = SQLiteManager.get_tables(db_name)
            return {
                'name': db_name,
                'tables_count': len(tables),
                'size': os.path.getsize(db_path) / 1024  # KB
            }
        except Exception:
            return {
                'name': db_name,
                'tables_count': 0,
                'size': 0
            }
    
    @staticmethod
    def create_database(db_name):
        """Create a new database."""
        db_path = SQLiteManager.get_database_path(db_name)
        if db_path.exists():
            return False, "Database already exists"
        with SQLiteManager.get_connection(db_name) as conn:
            pass  # Just creating the connection creates the database
        return True, "Database created successfully"
    
    @staticmethod
    def delete_database(db_name):
        """Delete a database."""
        db_path = SQLiteManager.get_database_path(db_name)
        if db_path.exists():
            os.remove(db_path)
            return True, "Database deleted successfully"
        return False, "Database not found"
    
    @staticmethod
    def database_exists(db_name):
        """Check if a database exists."""
        return SQLiteManager.get_database_path(db_name).exists()
    
    # Table Operations
    @staticmethod
    def get_tables(db_name):
        """Get all tables in a database."""
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            return [row[0] for row in cursor.fetchall()]
    
    @staticmethod
    def get_table_info(db_name, table_name):
        """Get column information for a table."""
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            return cursor.fetchall()
    
    @staticmethod
    def get_table_indexes(db_name, table_name):
        """Get indexes for a table."""
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(f'PRAGMA index_list("{table_name}")')
            return cursor.fetchall()
    
    @staticmethod
    def get_row_count(db_name, table_name):
        """Get the number of rows in a table."""
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            return cursor.fetchone()[0]
    
    @staticmethod
    def create_table(db_name, table_name, columns):
        """Create a new table."""
        sql = f'CREATE TABLE "{table_name}" ({columns})'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
        return sql
    
    @staticmethod
    def drop_table(db_name, table_name):
        """Drop a table."""
        sql = f'DROP TABLE "{table_name}"'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
        return sql
    
    @staticmethod
    def get_table_schema(db_name, table_name):
        """Get the CREATE statement for a table."""
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    # Column Operations
    @staticmethod
    def add_column(db_name, table_name, column_name, column_type, default_value=None):
        """Add a column to a table."""
        sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'
        if default_value:
            sql += f' DEFAULT {default_value}'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
        return sql
    
    @staticmethod
    def drop_column(db_name, table_name, column_name):
        """Drop a column from a table."""
        sql = f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
        return sql
    
    @staticmethod
    def add_columns_bulk(db_name, table_name, columns):
        """
        Add multiple columns to a table.
        columns: list of dicts with keys: name, type, constraint (optional), default (optional)
        """
        sql_statements = []
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            for col in columns:
                if not col.get('name') or not col.get('type'):
                    continue
                sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col["name"]}" {col["type"]}'
                if col.get('constraint'):
                    sql += f' {col["constraint"]}'
                if col.get('default'):
                    sql += f' DEFAULT {col["default"]}'
                cursor.execute(sql)
                sql_statements.append(sql)
            conn.commit()
        return sql_statements
    
    @staticmethod
    def modify_column(db_name, table_name, column_name, new_type, new_constraint=None):
        """
        Modify a column's type in SQLite by recreating the table.
        SQLite doesn't support ALTER COLUMN, so we need to:
        1. Create a new table with the modified column
        2. Copy data from old table
        3. Drop old table
        4. Rename new table to original name
        """
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            
            # Get current table schema
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = cursor.fetchall()
            
            # Get current indexes
            cursor.execute(f'PRAGMA index_list("{table_name}")')
            indexes = cursor.fetchall()
            
            # Build column definitions for new table
            column_defs = []
            column_names_list = []
            for col in columns:
                col_id, col_name, col_type, not_null, default_val, is_pk = col
                column_names_list.append(f'"{col_name}"')
                
                if col_name == column_name:
                    # This is the column we're modifying
                    col_def = f'"{col_name}" {new_type}'
                    if new_constraint:
                        col_def += f' {new_constraint}'
                    elif not_null and 'NOT NULL' not in (new_constraint or ''):
                        col_def += ' NOT NULL'
                else:
                    # Keep original column definition
                    col_def = f'"{col_name}" {col_type}'
                    if is_pk:
                        col_def += ' PRIMARY KEY'
                    if not_null and not is_pk:
                        col_def += ' NOT NULL'
                    if default_val is not None:
                        col_def += f' DEFAULT {default_val}'
                
                column_defs.append(col_def)
            
            temp_table = f'_temp_{table_name}_{column_name}'
            cols_str = ', '.join(column_defs)
            col_names_str = ', '.join(column_names_list)
            
            # Create new table
            cursor.execute(f'CREATE TABLE "{temp_table}" ({cols_str})')
            
            # Copy data
            cursor.execute(f'INSERT INTO "{temp_table}" ({col_names_str}) SELECT {col_names_str} FROM "{table_name}"')
            
            # Drop old table
            cursor.execute(f'DROP TABLE "{table_name}"')
            
            # Rename new table
            cursor.execute(f'ALTER TABLE "{temp_table}" RENAME TO "{table_name}"')
            
            conn.commit()
            
        return f'Modified column "{column_name}" to {new_type}'
    
    @staticmethod
    def drop_columns_bulk(db_name, table_name, column_names):
        """Drop multiple columns from a table."""
        sql_statements = []
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            for column_name in column_names:
                sql = f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"'
                cursor.execute(sql)
                sql_statements.append(sql)
            conn.commit()
        return sql_statements
    
    @staticmethod
    def get_csv_columns(content):
        """Get column names from CSV content."""
        reader = csv.DictReader(io.StringIO(content))
        return reader.fieldnames or []
    
    # Index Operations
    @staticmethod
    def create_index(db_name, table_name, index_name, columns, unique=False):
        """Create an index on a table."""
        unique_str = 'UNIQUE ' if unique else ''
        sql = f'CREATE {unique_str}INDEX "{index_name}" ON "{table_name}" ({columns})'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
        return sql
    
    @staticmethod
    def drop_index(db_name, index_name):
        """Drop an index."""
        sql = f'DROP INDEX "{index_name}"'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            conn.commit()
        return sql
    
    # Row Operations
    @staticmethod
    def get_rows(db_name, table_name, limit=50, offset=0):
        """Get rows from a table with pagination."""
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT rowid, * FROM "{table_name}" LIMIT {limit} OFFSET {offset}')
            return cursor.fetchall()
    
    @staticmethod
    def get_row_by_rowid(db_name, table_name, rowid):
        """Get a specific row by rowid."""
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT rowid, * FROM "{table_name}" WHERE rowid = ?', (rowid,))
            return cursor.fetchone()
    
    @staticmethod
    def insert_row(db_name, table_name, column_names, values):
        """Insert a row into a table."""
        placeholders = ', '.join(['?' for _ in column_names])
        cols_str = ', '.join([f'"{c}"' for c in column_names])
        sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, values)
            conn.commit()
        return sql
    
    @staticmethod
    def update_row(db_name, table_name, column_names, values, rowid):
        """Update a row in a table."""
        set_clauses = [f'"{col}" = ?' for col in column_names]
        sql = f'UPDATE "{table_name}" SET {", ".join(set_clauses)} WHERE rowid = ?'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, values + [rowid])
            conn.commit()
        return sql
    
    @staticmethod
    def delete_row(db_name, table_name, rowid):
        """Delete a row from a table."""
        sql = f'DELETE FROM "{table_name}" WHERE rowid = ?'
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (rowid,))
            conn.commit()
        return sql
    
    # Query Execution
    @staticmethod
    def execute_query(db_name, query):
        """Execute a SQL query and return results."""
        with SQLiteManager.get_connection(db_name, row_factory=True) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            
            # Check if query returns data (SELECT, PRAGMA, etc.)
            # cursor.description is not None when the query returns rows
            if cursor.description is not None:
                rows = cursor.fetchall()
                if rows:
                    columns = list(rows[0].keys())
                    data = [dict(row) for row in rows]
                else:
                    # Query returned no rows but has columns (empty result)
                    columns = [desc[0] for desc in cursor.description]
                    data = []
                return {
                    'type': 'select',
                    'columns': columns,
                    'rows': data,
                    'row_count': len(data)
                }
            else:
                conn.commit()
                return {
                    'type': 'modify',
                    'affected_rows': cursor.rowcount
                }
    
    # Export Operations
    @staticmethod
    def export_table_csv(db_name, table_name):
        """Export table data as CSV."""
        columns = SQLiteManager.get_table_info(db_name, table_name)
        column_names = [col[1] for col in columns]
        
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM "{table_name}"')
            rows = cursor.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(column_names)
        writer.writerows(rows)
        return output.getvalue()
    
    # Import Operations
    @staticmethod
    def import_csv(db_name, table_name, content):
        """Import CSV data into a table."""
        reader = csv.DictReader(io.StringIO(content))
        data = list(reader)
        
        if not data:
            return 0
        
        columns = list(data[0].keys())
        placeholders = ', '.join(['?' for _ in columns])
        cols_str = ', '.join([f'"{c}"' for c in columns])
        sql = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'
        
        with SQLiteManager.get_connection(db_name) as conn:
            cursor = conn.cursor()
            
            # Get table schema for better error messages
            schema = {}
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            for col_info in cursor.fetchall():
                schema[col_info[1]] = col_info[2]  # column name -> type
            
            for row_num, row in enumerate(data, start=2):  # Start at 2 (1 is header)
                try:
                    values = [row.get(col) for col in columns]
                    cursor.execute(sql, values)
                except Exception as e:
                    error_msg = str(e)
                    
                    # Build detailed error message
                    details = [f"Row {row_num}:"]
                    
                    # Show the problematic row data
                    row_data = []
                    for i, col in enumerate(columns):
                        value = row.get(col, '')
                        if len(value) > 50:
                            value = value[:47] + '...'
                        row_data.append(f"{col}='{value}'")
                    details.append(f"  Data: {{{', '.join(row_data)}}}")
                    
                    # Show expected column types
                    if 'datatype mismatch' in error_msg.lower():
                        type_info = []
                        for col in columns:
                            if col in schema:
                                type_info.append(f"{col} ({schema[col]})")
                            else:
                                type_info.append(f"{col} (unknown)")
                        details.append(f"  Expected types: {', '.join(type_info)}")
                    
                    details.append(f"  Database error: {error_msg}")
                    
                    raise Exception('\n'.join(details))
            
            conn.commit()
        
        return len(data)
    
    # Column type options for UI dropdowns
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
    
    COLUMN_CONSTRAINTS = [
        ('', 'None'),
        ('NOT NULL', 'NOT NULL'),
        ('UNIQUE', 'UNIQUE'),
        ('PRIMARY KEY', 'PRIMARY KEY'),
        ('PRIMARY KEY AUTOINCREMENT', 'PRIMARY KEY AUTOINCREMENT'),
    ]


class DatabaseOwnership(models.Model):
    """
    Track ownership of SQLite database files.
    The owner is the user who created the database.
    """
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_databases')
    database_name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    api_enabled = models.BooleanField(default=False)
    api_secret_key = models.CharField(max_length=64, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = 'Database Ownerships'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.database_name} (owned by {self.owner.username})"
    
    def generate_api_key(self):
        """Generate a new API key."""
        self.api_secret_key = secrets.token_urlsafe(32)
        self.save()
        return self.api_secret_key

    @classmethod
    def get_owner(cls, database_name):
        """Get the owner of a database."""
        try:
            ownership = cls.objects.get(database_name=database_name)
            return ownership.owner
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def is_owner(cls, user, database_name):
        """Check if user is the owner of a database."""
        return cls.objects.filter(owner=user, database_name=database_name).exists()
    
    @classmethod
    def create_ownership(cls, user, database_name):
        """Create ownership record for a new database."""
        return cls.objects.create(owner=user, database_name=database_name)
    
    @classmethod
    def transfer_ownership(cls, database_name, new_owner):
        """Transfer ownership of a database to another user."""
        try:
            ownership = cls.objects.get(database_name=database_name)
            ownership.owner = new_owner
            ownership.save()
            return True
        except cls.DoesNotExist:
            # Create ownership record for legacy database
            cls.objects.create(owner=new_owner, database_name=database_name)
            return True
    
    @classmethod
    def database_name_exists(cls, database_name):
        """Check if a database name is already registered (owned by someone)."""
        return cls.objects.filter(database_name=database_name).exists()
    
    @classmethod
    def claim_ownership(cls, user, database_name):
        """Claim ownership of a legacy database (one without an owner record)."""
        if cls.objects.filter(database_name=database_name).exists():
            return False, "Database already has an owner"
        if not SQLiteManager.database_exists(database_name):
            return False, "Database does not exist"
        cls.objects.create(owner=user, database_name=database_name)
        return True, "Ownership claimed successfully"


class DatabasePermission(models.Model):
    """
    Manage shared permissions for databases.
    Allows database owners to share access with other users.
    """
    PERMISSION_CHOICES = [
        ('read', 'Read Only'),
        ('write', 'Read & Write'),
        ('admin', 'Full Access (Admin)'),
    ]
    
    database_name = models.CharField(max_length=255)
    granted_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='database_permissions')
    granted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='permissions_granted')
    permission_level = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default='read')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = 'Database Permissions'
        unique_together = ['database_name', 'granted_to']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.granted_to.username} -> {self.database_name} ({self.permission_level})"
    
    @classmethod
    def get_permission_level(cls, user, database_name):
        """Get user's permission level for a database."""
        try:
            perm = cls.objects.get(granted_to=user, database_name=database_name)
            return perm.permission_level
        except cls.DoesNotExist:
            return None
    
    @classmethod
    def has_read_permission(cls, user, database_name):
        """Check if user has at least read permission."""
        return cls.objects.filter(
            granted_to=user,
            database_name=database_name,
            permission_level__in=['read', 'write', 'admin']
        ).exists()
    
    @classmethod
    def has_write_permission(cls, user, database_name):
        """Check if user has at least write permission."""
        return cls.objects.filter(
            granted_to=user,
            database_name=database_name,
            permission_level__in=['write', 'admin']
        ).exists()
    
    @classmethod
    def has_admin_permission(cls, user, database_name):
        """Check if user has admin permission."""
        return cls.objects.filter(
            granted_to=user,
            database_name=database_name,
            permission_level='admin'
        ).exists()
    
    @classmethod
    def grant_permission(cls, database_name, granted_by, granted_to, permission_level='read'):
        """Grant permission to a user for a database."""
        perm, created = cls.objects.update_or_create(
            database_name=database_name,
            granted_to=granted_to,
            defaults={
                'granted_by': granted_by,
                'permission_level': permission_level
            }
        )
        return perm
    
    @classmethod
    def revoke_permission(cls, database_name, user):
        """Revoke user's permission for a database."""
        return cls.objects.filter(database_name=database_name, granted_to=user).delete()
    
    @classmethod
    def get_shared_users(cls, database_name):
        """Get all users who have been granted permission to a database."""
        return cls.objects.filter(database_name=database_name).select_related('granted_to', 'granted_by')


class DatabaseAccess(models.Model):
    """
    Track which users have access to which databases and what operations they performed.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='database_accesses')
    database_name = models.CharField(max_length=255)
    last_accessed = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = 'Database Accesses'
        unique_together = ['user', 'database_name']
        ordering = ['-last_accessed']
    
    def __str__(self):
        return f"{self.user.username} - {self.database_name}"
    
    @classmethod
    def log_access(cls, user, database_name):
        """Log database access for a user."""
        cls.objects.update_or_create(
            user=user,
            database_name=database_name,
            defaults={}
        )


class QueryHistory(models.Model):
    """
    Store history of executed queries for audit purposes.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='query_history')
    database_name = models.CharField(max_length=255)
    query = models.TextField()
    executed_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = 'Query Histories'
        ordering = ['-executed_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.database_name} - {self.executed_at}"
    
    @classmethod
    def log_query(cls, user, database_name, query, success=True, error_message=None):
        """Log a query execution."""
        return cls.objects.create(
            user=user,
            database_name=database_name,
            query=query,
            success=success,
            error_message=error_message
        )


class Dashboard(models.Model):
    """
    Represents a collection of charts that users can organize.
    Users can create multiple dashboards to group charts by purpose/project.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboards')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-is_default', 'order', '-created_at']
        unique_together = ['user', 'name']
    
    def __str__(self):
        return f"{self.user.username} - {self.name}"
    
    def save(self, *args, **kwargs):
        # Ensure only one default dashboard per user
        if self.is_default:
            Dashboard.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_or_create_default(cls, user):
        """Get or create a default dashboard for a user."""
        dashboard, created = cls.objects.get_or_create(
            user=user,
            is_default=True,
            defaults={'name': 'My Dashboard', 'description': 'Default dashboard'}
        )
        return dashboard


class DashboardChart(models.Model):
    """
    Store chart configurations for user dashboards.
    """
    CHART_TYPES = [
        ('bar', 'Bar Chart'),
        ('line', 'Line Chart'),
        ('pie', 'Pie Chart'),
        ('doughnut', 'Doughnut Chart'),
        ('polarArea', 'Polar Area Chart'),
        ('radar', 'Radar Chart'),
    ]
    
    REFRESH_CHOICES = [
        (0, 'No auto-refresh'),
        (30, '30 seconds'),
        (60, '1 minute'),
        (300, '5 minutes'),
        (600, '10 minutes'),
        (1800, '30 minutes'),
        (3600, '1 hour'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboard_charts')
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name='charts', null=True, blank=True)
    title = models.CharField(max_length=255)
    database_name = models.CharField(max_length=255)
    query = models.TextField()
    chart_type = models.CharField(max_length=20, choices=CHART_TYPES, default='bar')
    auto_refresh = models.IntegerField(choices=REFRESH_CHOICES, default=0, help_text='Auto-refresh interval in seconds')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order', '-created_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"
    
    def save(self, *args, **kwargs):
        # Auto-assign to default dashboard if none specified
        if not self.dashboard and self.user:
            self.dashboard = Dashboard.get_or_create_default(self.user)
        super().save(*args, **kwargs)
    
    def execute_query(self):
        """Execute the chart query and return results."""
        try:
            with SQLiteManager.get_connection(self.database_name, row_factory=True) as conn:
                cursor = conn.cursor()
                cursor.execute(self.query)
                rows = cursor.fetchall()
                if rows:
                    columns = list(rows[0].keys())
                    data = [dict(row) for row in rows]
                    return {'success': True, 'columns': columns, 'data': data}
                return {'success': True, 'columns': [], 'data': []}
        except Exception as e:
            return {'success': False, 'error': str(e)}
