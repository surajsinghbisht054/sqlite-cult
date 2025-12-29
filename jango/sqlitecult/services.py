"""
Service layer for SQLite Cult application.
Contains business logic separated from views for better testability and reusability.
"""
from .models import SQLiteManager, SqliteFile
from .constants import WRITE_SQL_COMMANDS


class PermissionService:
    """
    Service for handling permission-related operations.
    Provides a clean interface for permission checks.
    """
    
    @staticmethod
    def get_user_database_context(user, db_name):
        """
        Get common permission context for a user and database.
        
        Returns:
            dict: Permission context with is_owner, is_admin, can_write, can_manage, has_owner
        """
        sqlite_file = SqliteFile.get_by_actual_filename(db_name)
        is_admin = user.is_superuser or user.is_staff
        
        if sqlite_file:
            is_owner = sqlite_file.owner == user
            can_write = is_owner or is_admin or sqlite_file.user_can_write(user)
            can_manage = is_owner or is_admin
            has_owner = True
        else:
            is_owner = False
            can_write = is_admin
            can_manage = is_admin
            has_owner = False
        
        return {
            'is_owner': is_owner,
            'is_admin': is_admin,
            'can_write': can_write,
            'can_manage': can_manage,
            'has_owner': has_owner,
            'sqlite_file': sqlite_file,
        }
    
    @staticmethod
    def get_api_settings(db_name):
        """
        Get API settings for a database.
        
        Returns:
            dict: API settings with api_enabled, api_token, and api_permissions
        """
        sqlite_file = SqliteFile.get_by_actual_filename(db_name)
        
        if sqlite_file:
            return {
                'api_enabled': sqlite_file.api_enabled,
                'api_token': sqlite_file.api_token or '',
                'api_permissions': sqlite_file.api_permissions or [],
            }
        return {
            'api_enabled': False,
            'api_token': '',
            'api_permissions': [],
        }
    
    @staticmethod
    def is_write_query(query):
        """
        Check if a SQL query is a write operation.
        
        Args:
            query: SQL query string
            
        Returns:
            bool: True if query modifies data
        """
        query_upper = query.upper().strip()
        return any(query_upper.startswith(cmd) for cmd in WRITE_SQL_COMMANDS)


class TableService:
    """
    Service for table-related operations.
    """
    
    @staticmethod
    def get_table_info_context(db_name, table_name):
        """
        Get common table information for views.
        
        Returns:
            dict: Table context with columns, column_names, indexes
        """
        columns = SQLiteManager.get_table_info(db_name, table_name)
        column_names = [col[1] for col in columns]
        indexes = SQLiteManager.get_table_indexes(db_name, table_name)
        
        return {
            'columns': columns,
            'column_names': column_names,
            'indexes': indexes,
        }
    
    @staticmethod
    def get_paginated_rows(db_name, table_name, page=1, per_page=50):
        """
        Get paginated rows from a table.
        
        Returns:
            dict: Pagination context with rows, total_rows, total_pages, page, per_page
        """
        offset = (page - 1) * per_page
        rows = SQLiteManager.get_rows(db_name, table_name, per_page, offset)
        total_rows = SQLiteManager.get_row_count(db_name, table_name)
        total_pages = (total_rows + per_page - 1) // per_page
        
        return {
            'rows': rows,
            'total_rows': total_rows,
            'total_pages': total_pages,
            'page': page,
            'per_page': per_page,
        }
    
    @staticmethod
    def build_column_definitions(col_names, col_types, col_constraints, col_defaults):
        """
        Build column definition SQL from form data.
        
        Returns:
            str: SQL column definitions
        """
        column_defs = []
        for i, name in enumerate(col_names):
            if name.strip():
                col_def = f'"{name.strip()}" {col_types[i]}'
                if i < len(col_constraints) and col_constraints[i]:
                    col_def += f' {col_constraints[i]}'
                if i < len(col_defaults) and col_defaults[i]:
                    col_def += f' DEFAULT {col_defaults[i]}'
                column_defs.append(col_def)
        return ', '.join(column_defs)
    
    @staticmethod
    def parse_column_data(col_names, col_types, col_constraints, col_defaults):
        """
        Parse column form data into a list of column dictionaries.
        
        Returns:
            list: List of column dicts with name, type, constraint, default
        """
        columns = []
        for i, name in enumerate(col_names):
            if name.strip():
                columns.append({
                    'name': name.strip(),
                    'type': col_types[i] if i < len(col_types) else 'TEXT',
                    'constraint': col_constraints[i] if i < len(col_constraints) else '',
                    'default': col_defaults[i] if i < len(col_defaults) else ''
                })
        return columns


class RowService:
    """
    Service for row serialization (used by API views).
    """
    
    @staticmethod
    def serialize_row(row, columns):
        """
        Serialize a database row to a dictionary.
        
        Args:
            row: Tuple from database (rowid, col1, col2, ...)
            columns: List of column names
            
        Returns:
            dict: Row as dictionary with rowid and column values
        """
        if not row:
            return None
        row_dict = {'rowid': row[0]}
        for i, col in enumerate(columns):
            row_dict[col] = row[i + 1] if i + 1 < len(row) else None
        return row_dict
    
    @staticmethod
    def serialize_rows(rows, columns):
        """
        Serialize multiple rows to a list of dictionaries.
        
        Args:
            rows: List of tuples from database
            columns: List of column names
            
        Returns:
            list: List of row dictionaries
        """
        return [RowService.serialize_row(row, columns) for row in rows]
