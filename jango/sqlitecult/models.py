import os
import sqlite3
import json
import csv
import io
from pathlib import Path
from contextlib import contextmanager
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings


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
            
            if query.strip().upper().startswith('SELECT'):
                rows = cursor.fetchall()
                if rows:
                    columns = list(rows[0].keys())
                    data = [dict(row) for row in rows]
                else:
                    columns = []
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
            for row in data:
                values = [row.get(col) for col in columns]
                cursor.execute(sql, values)
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
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dashboard_charts')
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name='charts', null=True, blank=True)
    title = models.CharField(max_length=255)
    database_name = models.CharField(max_length=255)
    query = models.TextField()
    chart_type = models.CharField(max_length=20, choices=CHART_TYPES, default='bar')
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
