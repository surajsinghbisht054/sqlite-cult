import os
import sqlite3
import json
import csv
import io
import secrets
import uuid
from pathlib import Path
from contextlib import contextmanager
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import PermissionDenied
from guardian.shortcuts import assign_perm, remove_perm, get_users_with_perms, get_perms


def generate_unique_filename():
    """Generate a unique filename for SQLite database files."""
    return f"db_{uuid.uuid4().hex[:16]}"


class SqliteFile(models.Model):
    """
    Represents an SQLite database file.
    Uses django-guardian for object-level permissions.
    """
    # Unique internal filename (hidden from users, auto-generated)
    filename = models.CharField(
        max_length=64, 
        unique=True, 
        editable=False,
        help_text="Internal unique filename for the SQLite file"
    )
    
    # User-friendly display name
    name = models.CharField(
        max_length=255,
        help_text="Display name for the database"
    )
    
    # Owner of the database
    owner = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='owned_sqlite_files'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # API Configuration
    api_enabled = models.BooleanField(default=False)
    api_token = models.TextField(blank=True, null=True, help_text="JWT token for API access")
    api_permissions = models.JSONField(
        default=list,
        blank=True,
        help_text="List of permissions for API: read, create, update, delete"
    )
    
    class Meta:
        verbose_name = 'SQLite File'
        verbose_name_plural = 'SQLite Files'
        ordering = ['-created_at']
        # Define custom permissions for django-guardian
        permissions = (
            ('view_database', 'Can view SQLite database'),
            ('add_data', 'Can add data to tables'),
            ('change_data', 'Can modify data in tables'),
            ('delete_data', 'Can delete data from tables'),
        )
    
    def __str__(self):
        return f"{self.name} (owned by {self.owner.username})"
    
    def save(self, *args, **kwargs):
        if not self.filename:
            self.filename = generate_unique_filename()
        super().save(*args, **kwargs)
    
    def get_file_path(self):
        """Get the full path to the SQLite file."""
        return SQLiteManager.get_database_path(f"{self.filename}.db")
    
    def get_actual_filename(self):
        """Get the actual filename with extension."""
        return f"{self.filename}.db"
    
    # Permission Management Methods
    def grant_permission(self, user, permission):
        """
        Grant a specific permission to a user.
        
        Args:
            user: The user to grant permission to
            permission: One of 'view_database', 'add_data', 'change_data', 'delete_data'
        """
        assign_perm(permission, user, self)
    
    def revoke_permission(self, user, permission):
        """Revoke a specific permission from a user."""
        remove_perm(permission, user, self)
    
    def revoke_all_permissions(self, user):
        """Revoke all permissions from a user."""
        for perm in ['view_database', 'add_data', 'change_data', 'delete_data']:
            remove_perm(perm, user, self)
    
    def get_users_with_permissions(self):
        """Get all users who have any permissions on this database."""
        return get_users_with_perms(self, attach_perms=True)
    
    def get_user_permissions(self, user):
        """Get all permissions a specific user has on this database."""
        return get_perms(user, self)
    
    def user_can_view(self, user):
        """Check if user can view this database."""
        if self._is_privileged_user(user):
            return True
        return user.has_perm('view_database', self)
    
    def user_can_add(self, user):
        """Check if user can add data to this database."""
        if self._is_privileged_user(user):
            return True
        return user.has_perm('add_data', self)
    
    def user_can_change(self, user):
        """Check if user can modify data in this database."""
        if self._is_privileged_user(user):
            return True
        return user.has_perm('change_data', self)
    
    def user_can_delete(self, user):
        """Check if user can delete data from this database."""
        if self._is_privileged_user(user):
            return True
        return user.has_perm('delete_data', self)
    
    def user_can_write(self, user):
        """Check if user can perform any write operation."""
        if self._is_privileged_user(user):
            return True
        return any([
            user.has_perm('add_data', self),
            user.has_perm('change_data', self),
            user.has_perm('delete_data', self)
        ])
    
    def _is_privileged_user(self, user):
        """Check if user is owner, superuser, or staff."""
        return user.is_superuser or user.is_staff or self.owner == user
    
    # API Token Management
    def generate_api_token(self):
        """Generate a new JWT token for API access."""
        from .jwt_utils import JWTManager
        
        permissions = self.api_permissions if self.api_permissions else []
        self.api_token = JWTManager.generate_token(
            sqlite_file_id=self.id,
            database_name=self.name,
            permissions=permissions
        )
        self.save(update_fields=['api_token'])
        return self.api_token
    
    def regenerate_api_token(self):
        """Regenerate the API token with current permissions."""
        return self.generate_api_token()
    
    def update_api_permissions(self, permissions):
        """
        Update API permissions and regenerate token.
        
        Args:
            permissions: List of permissions (read, create, update, delete)
        """
        self.api_permissions = permissions
        self.save(update_fields=['api_permissions'])
        if self.api_enabled:
            self.generate_api_token()
    
    def enable_api(self, permissions=None):
        """Enable API access with specified permissions."""
        if permissions is None:
            permissions = ['read']  # Default to read-only
        self.api_enabled = True
        self.api_permissions = permissions
        self.save(update_fields=['api_enabled', 'api_permissions'])
        self.generate_api_token()
    
    def disable_api(self):
        """Disable API access."""
        self.api_enabled = False
        self.api_token = None
        self.save(update_fields=['api_enabled', 'api_token'])
    
    # Class methods for querying
    @classmethod
    def get_by_filename(cls, filename):
        """Get SqliteFile by internal filename (without extension)."""
        filename = filename.replace('.db', '').replace('.sqlite', '').replace('.sqlite3', '')
        return cls.objects.filter(filename=filename).first()
    
    @classmethod
    def get_by_actual_filename(cls, actual_filename):
        """Get SqliteFile by actual filename (with extension)."""
        filename = actual_filename
        for ext in ['.db', '.sqlite', '.sqlite3']:
            filename = filename.replace(ext, '')
        return cls.objects.filter(filename=filename).first()
    
    @classmethod
    def get_accessible_for_user(cls, user):
        """
        Get all databases accessible to a user.
        
        For superusers/staff: returns all databases
        For regular users: returns owned databases + databases with view permission
        """
        if user.is_superuser or user.is_staff:
            return cls.objects.all()
        
        # Get owned databases
        owned = cls.objects.filter(owner=user)
        
        # Get databases with view permission using guardian
        from guardian.shortcuts import get_objects_for_user
        with_permission = get_objects_for_user(user, 'sqlitecult.view_database', klass=cls)
        
        # Combine and deduplicate
        return (owned | with_permission).distinct()
    
    @classmethod
    def create_database(cls, user, name):
        """
        Create a new database with the given name.
        
        Args:
            user: The owner of the database
            name: Display name for the database
            
        Returns:
            tuple: (SqliteFile instance, success boolean, message)
        """
        # Create the model instance first
        sqlite_file = cls(owner=user, name=name)
        sqlite_file.save()  # This will generate the unique filename
        
        # Now create the actual SQLite file
        db_path = sqlite_file.get_file_path()
        if db_path.exists():
            # Shouldn't happen due to unique filename, but handle it
            sqlite_file.delete()
            return None, False, "Database file already exists"
        
        try:
            with SQLiteManager.get_connection(sqlite_file.get_actual_filename()) as conn:
                pass  # Just creating the connection creates the database
            return sqlite_file, True, "Database created successfully"
        except Exception as e:
            sqlite_file.delete()
            return None, False, str(e)
    
    def delete_database(self):
        """Delete the database file and the model instance."""
        db_path = self.get_file_path()
        if db_path.exists():
            os.remove(db_path)
        self.delete()
    
    def transfer_ownership(self, new_owner):
        """Transfer ownership to another user."""
        self.owner = new_owner
        self.save(update_fields=['owner'])


class DatabasePermissionChecker:
    """
    Centralized permission checking for database operations.
    Handles the authorization logic for all database access.
    Now works with SqliteFile model and django-guardian.
    """
    
    @staticmethod
    def is_superuser_or_staff(user):
        """Check if user is a superuser or staff member."""
        return user.is_superuser or user.is_staff
    
    @staticmethod
    def get_sqlite_file(database_name):
        """Get SqliteFile instance by actual filename."""
        return SqliteFile.get_by_actual_filename(database_name)
    
    @staticmethod
    def can_access_database(user, database_name, require_write=False, require_admin=False):
        """
        Check if a user can access a database.
        
        Args:
            user: The user requesting access
            database_name: The actual filename of the database
            require_write: If True, requires write permission
            require_admin: If True, requires owner/admin access
        
        Returns:
            tuple: (can_access: bool, reason: str)
        """
        # Superusers and staff can access everything
        if user.is_superuser or user.is_staff:
            return True, "Admin access"
        
        sqlite_file = DatabasePermissionChecker.get_sqlite_file(database_name)
        
        if not sqlite_file:
            # Legacy database without SqliteFile record
            return False, "No access permission"
        
        # Check if user is the owner
        if sqlite_file.owner == user:
            return True, "Owner access"
        
        if require_admin:
            # Only owner/superuser/staff can perform admin operations
            return False, "Admin permission required"
        
        if require_write:
            if sqlite_file.user_can_write(user):
                return True, "Write permission"
            return False, "Write permission required"
        
        # Check view permission
        if sqlite_file.user_can_view(user):
            return True, "View permission"
        
        return False, "No access permission"
    
    @staticmethod
    def get_accessible_databases(user):
        """
        Get list of databases a user can access.
        
        Returns:
            tuple: (list of actual filenames, has_full_access boolean)
        """
        if user.is_superuser or user.is_staff:
            return SQLiteManager.list_databases(), True
        
        accessible_files = SqliteFile.get_accessible_for_user(user)
        accessible = [sf.get_actual_filename() for sf in accessible_files]
        
        # Filter to only include databases that actually exist
        existing = set(SQLiteManager.list_databases())
        accessible = [db for db in accessible if db in existing]
        
        return accessible, False
    
    @staticmethod
    def check_database_name_available(user, name):
        """
        Check if a database name is available for a user to use.
        
        Note: With the new SqliteFile model, the actual filename is auto-generated
        and unique. This method checks if the display name is already in use by the user.
        
        Returns:
            tuple: (is_available: bool, error_message: str or None)
        """
        # Check if user already has a database with this name
        if SqliteFile.objects.filter(owner=user, name=name).exists():
            return False, "You already have a database with this name."
        
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
    def get_csv_columns(content, check_duplicates=False):
        """Get column names from CSV content.
        
        Args:
            content: CSV file content as string
            check_duplicates: If True, raises ValueError on duplicate columns
            
        Returns:
            List of column names (stripped of whitespace)
            
        Raises:
            ValueError: If check_duplicates=True and duplicate columns found
        """
        # Use proper CSV parsing to get headers
        reader = csv.reader(io.StringIO(content))
        try:
            raw_columns = next(reader)
        except StopIteration:
            return []
        
        # Strip whitespace from all column names
        stripped_columns = [col.strip() for col in raw_columns]
        
        if check_duplicates:
            # Check for duplicates after stripping
            seen = {}
            duplicates = []
            for col in stripped_columns:
                if col in seen:
                    if col not in duplicates:
                        duplicates.append(col)
                seen[col] = True
            
            if duplicates:
                raise ValueError(f"Duplicate column names found in CSV: {', '.join(duplicates)}")
        
        return stripped_columns
    
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
        
        # Get original columns and create stripped versions
        original_columns = list(data[0].keys())
        columns = [col.strip() for col in original_columns]
        
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
                    # Use original column names to get values from row dict
                    values = [row.get(orig_col) for orig_col in original_columns]
                    cursor.execute(sql, values)
                except Exception as e:
                    error_msg = str(e)
                    
                    # Build detailed error message
                    details = [f"Row {row_num}:"]
                    
                    # Show the problematic row data
                    row_data = []
                    for i, col in enumerate(columns):
                        orig_col = original_columns[i]
                        value = row.get(orig_col, '')
                        if value and len(value) > 50:
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
    
    # Import column type options from constants for UI dropdowns
    # (keeping for backward compatibility)
    from .constants import COLUMN_TYPES as _COLUMN_TYPES, COLUMN_CONSTRAINTS as _COLUMN_CONSTRAINTS
    COLUMN_TYPES = _COLUMN_TYPES
    COLUMN_CONSTRAINTS = _COLUMN_CONSTRAINTS


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
    # Import from constants for DRY (keeping as class attributes for Django model compatibility)
    from .constants import CHART_TYPES as _CHART_TYPES, REFRESH_INTERVALS as _REFRESH_INTERVALS
    CHART_TYPES = _CHART_TYPES
    REFRESH_CHOICES = _REFRESH_INTERVALS
    
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
