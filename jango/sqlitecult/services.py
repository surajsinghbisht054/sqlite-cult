"""
Service layer for SQLite Cult application.
Contains business logic separated from views for better testability and reusability.
"""
from django.contrib.auth.models import User
from .models import (
    SQLiteManager, SqliteFile,
    DatabaseAccess, QueryHistory, Dashboard, DashboardChart
)
from .constants import ErrorMessages, SuccessMessages, WRITE_SQL_COMMANDS


class PermissionService:
    """
    Service for handling permission-related operations.
    Provides a clean interface for permission checks.
    """
    
    @staticmethod
    def get_user_database_context(user, db_name):
        """
        Get common permission context for a user and database.
        Reduces code duplication in views.
        
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
    Provides business logic for table management.
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
        
        Args:
            col_names: List of column names
            col_types: List of column types
            col_constraints: List of column constraints
            col_defaults: List of default values
            
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
    Service for row operations.
    Handles row serialization and deserialization.
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
    
    @staticmethod
    def extract_form_values(request, column_names):
        """
        Extract column values from a POST request.
        
        Args:
            request: HTTP request object
            column_names: List of column names to extract
            
        Returns:
            list: List of values (None for empty strings)
        """
        values = []
        for col in column_names:
            val = request.POST.get(col, '')
            values.append(val if val else None)
        return values


class DatabaseService:
    """
    Service for database-level operations.
    """
    
    @staticmethod
    def get_database_list_context(user):
        """
        Get database list with ownership info for a user.
        
        Returns:
            list: List of database info dicts
        """
        from .models import DatabasePermissionChecker
        
        accessible_db_names, has_full_access = DatabasePermissionChecker.get_accessible_databases(user)
        
        db_info = []
        for db_name in accessible_db_names:
            info = SQLiteManager.get_database_info(db_name)
            sqlite_file = SqliteFile.get_by_actual_filename(db_name)
            
            if sqlite_file:
                info['owner'] = sqlite_file.owner.username
                info['is_owner'] = sqlite_file.owner == user
                info['display_name'] = sqlite_file.name
            else:
                info['owner'] = 'Unknown'
                info['is_owner'] = False
                info['display_name'] = db_name
            
            info['is_admin'] = user.is_superuser or user.is_staff
            
            if not info['is_owner'] and not info['is_admin']:
                if sqlite_file:
                    perms = sqlite_file.get_user_permissions(user)
                    info['permission_level'] = 'write' if any(p in perms for p in ['add_data', 'change_data', 'delete_data']) else 'read'
                else:
                    info['permission_level'] = None
            else:
                info['permission_level'] = 'owner' if info['is_owner'] else 'admin'
            
            db_info.append(info)
        
        return db_info, has_full_access
    
    @staticmethod
    def get_tables_context(db_name):
        """
        Get table information for a database.
        
        Returns:
            list: List of table info dicts
        """
        tables = SQLiteManager.get_tables(db_name)
        table_info = []
        for table in tables:
            columns = SQLiteManager.get_table_info(db_name, table)
            row_count = SQLiteManager.get_row_count(db_name, table)
            table_info.append({
                'name': table,
                'columns': columns,
                'row_count': row_count
            })
        return table_info
    
    @staticmethod
    def cleanup_database_records(db_name):
        """
        Clean up all related records when a database is deleted.
        """
        sqlite_file = SqliteFile.get_by_actual_filename(db_name)
        if sqlite_file:
            sqlite_file.delete()
        
        DatabaseAccess.objects.filter(database_name=db_name).delete()
        QueryHistory.objects.filter(database_name=db_name).delete()
        DashboardChart.objects.filter(database_name=db_name).delete()


class QueryService:
    """
    Service for query execution and history.
    """
    
    @staticmethod
    def execute_and_log(user, db_name, query):
        """
        Execute a query and log it to history.
        
        Returns:
            tuple: (success, result_or_error)
        """
        try:
            result = SQLiteManager.execute_query(db_name, query)
            QueryHistory.log_query(user, db_name, query)
            return True, result
        except Exception as e:
            QueryHistory.log_query(user, db_name, query, False, str(e))
            return False, str(e)


class ImportService:
    """
    Service for import operations.
    """
    
    @staticmethod
    def preview_csv_import(db_name, table_name, file_content):
        """
        Preview a CSV import and detect missing columns.
        
        Returns:
            dict: Preview data with file_columns, table_columns, missing_columns
        """
        file_columns = SQLiteManager.get_csv_columns(file_content)
        table_columns_info = SQLiteManager.get_table_info(db_name, table_name)
        table_columns = [col[1] for col in table_columns_info]
        missing_columns = [col for col in file_columns if col not in table_columns]
        
        return {
            'file_columns': file_columns,
            'table_columns': table_columns,
            'missing_columns': missing_columns,
            'has_missing': len(missing_columns) > 0,
        }
