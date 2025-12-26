from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.generic import TemplateView, FormView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.urls import reverse_lazy
from pygments import highlight
from pygments.lexers import SqlLexer
from pygments.formatters import HtmlFormatter

from .models import (
    DatabaseAccess, QueryHistory, SQLiteManager, DashboardChart, Dashboard,
    DatabaseOwnership, DatabasePermission, DatabasePermissionChecker
)
from .forms import CreateDatabaseForm
from .mixins import (
    DatabasePermissionMixin, DatabaseReadPermissionMixin,
    DatabaseWritePermissionMixin, DatabaseAdminPermissionMixin,
    DatabaseOwnerOrAdminMixin
)


# Authentication Views
class CustomLoginView(LoginView):
    template_name = 'auth/login.html'
    redirect_authenticated_user = True
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['registration_enabled'] = getattr(settings, 'SQLITE_CULT_ENABLE_REGISTRATION', True)
        return context


class CustomLogoutView(LogoutView):
    next_page = 'login'


class RegisterView(FormView):
    template_name = 'auth/register.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    
    def dispatch(self, request, *args, **kwargs):
        # Check if registration is enabled
        if not getattr(settings, 'SQLITE_CULT_ENABLE_REGISTRATION', True):
            messages.error(request, 'Registration is disabled.')
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Account created successfully. Please log in.')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['registration_enabled'] = getattr(settings, 'SQLITE_CULT_ENABLE_REGISTRATION', True)
        return context


# Database Views
class DatabaseListView(LoginRequiredMixin, TemplateView):
    template_name = 'database/list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get accessible databases based on user permissions
        accessible_db_names, has_full_access = DatabasePermissionChecker.get_accessible_databases(user)
        
        # Build database info with ownership details
        db_info = []
        for db_name in accessible_db_names:
            info = SQLiteManager.get_database_info(db_name)
            
            # Add ownership information
            owner = DatabaseOwnership.get_owner(db_name)
            info['owner'] = owner.username if owner else 'Unknown'
            info['is_owner'] = owner == user if owner else False
            info['is_admin'] = user.is_superuser or user.is_staff
            
            # Get user's permission level if not owner
            if not info['is_owner'] and not info['is_admin']:
                perm_level = DatabasePermission.get_permission_level(user, db_name)
                info['permission_level'] = perm_level
            else:
                info['permission_level'] = 'owner' if info['is_owner'] else 'admin'
            
            db_info.append(info)
        
        context['databases'] = db_info
        context['create_form'] = CreateDatabaseForm()
        context['has_full_access'] = has_full_access
        context['is_admin'] = user.is_superuser or user.is_staff
        return context


class CreateDatabaseView(LoginRequiredMixin, View):
    def post(self, request):
        form = CreateDatabaseForm(request.POST)
        if form.is_valid():
            db_name = form.cleaned_data['name']
            
            # Check if database name is available
            is_available, error_msg = DatabasePermissionChecker.check_database_name_available(
                request.user, db_name
            )
            
            if not is_available:
                messages.error(request, error_msg)
                return redirect('database_list')
            
            success, message = SQLiteManager.create_database(db_name)
            if success:
                # Register ownership
                DatabaseOwnership.create_ownership(request.user, db_name)
                DatabaseAccess.log_access(request.user, db_name)
                messages.success(request, f'Database "{db_name}" created successfully.')
            else:
                messages.error(request, f'Failed to create database: {message}')
        else:
            messages.error(request, 'Invalid database name.')
        return redirect('database_list')


class DeleteDatabaseView(DatabaseOwnerOrAdminMixin, View):
    """Only database owner or admin can delete a database."""
    def post(self, request, db_name):
        success, message = SQLiteManager.delete_database(db_name)
        if success:
            # Clean up all related records
            DatabaseAccess.objects.filter(database_name=db_name).delete()
            DatabaseOwnership.objects.filter(database_name=db_name).delete()
            DatabasePermission.objects.filter(database_name=db_name).delete()
            messages.success(request, f'Database "{db_name}" deleted successfully.')
        else:
            messages.error(request, f'Database "{db_name}" not found.')
        return redirect('database_list')


class DatabaseDetailView(DatabaseReadPermissionMixin, TemplateView):
    template_name = 'database/detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        db_name = kwargs['db_name']
        user = self.request.user
        
        DatabaseAccess.log_access(user, db_name)
        
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
        
        # Determine user's permission level for UI display
        is_owner = DatabaseOwnership.is_owner(user, db_name)
        is_admin = user.is_superuser or user.is_staff
        can_write = is_owner or is_admin or DatabasePermission.has_write_permission(user, db_name)
        can_manage = is_owner or is_admin
        has_owner = DatabaseOwnership.get_owner(db_name) is not None
        
        context['db_name'] = db_name
        context['tables'] = table_info
        context['column_types'] = SQLiteManager.COLUMN_TYPES
        context['column_constraints'] = SQLiteManager.COLUMN_CONSTRAINTS
        context['is_owner'] = is_owner
        context['is_admin'] = is_admin
        context['can_write'] = can_write
        context['can_manage'] = can_manage
        context['has_owner'] = has_owner
        
        # Add API settings for owners
        context['api_enabled'] = False
        context['api_key'] = ''
        if is_owner or is_admin:
            try:
                ownership = DatabaseOwnership.objects.get(database_name=db_name)
                context['api_enabled'] = ownership.api_enabled
                context['api_key'] = ownership.api_secret_key or ''
            except DatabaseOwnership.DoesNotExist:
                pass
                
        return context


# Table Views
class CreateTableView(DatabaseWritePermissionMixin, View):
    """Requires write permission to create tables."""
    def post(self, request, db_name):
        table_name = request.POST.get('table_name', '').strip()
        
        # Check if using visual builder or raw SQL
        use_visual = request.POST.get('use_visual', 'false') == 'true'
        
        if use_visual:
            # Build columns from visual form
            col_names = request.POST.getlist('col_name[]')
            col_types = request.POST.getlist('col_type[]')
            col_constraints = request.POST.getlist('col_constraint[]')
            col_defaults = request.POST.getlist('col_default[]')
            
            if not table_name or not col_names or not col_names[0]:
                messages.error(request, 'Table name and at least one column are required.')
                return redirect('database_detail', db_name=db_name)
            
            column_defs = []
            for i, name in enumerate(col_names):
                if name.strip():
                    col_def = f'"{name.strip()}" {col_types[i]}'
                    if col_constraints[i]:
                        col_def += f' {col_constraints[i]}'
                    if col_defaults[i]:
                        col_def += f' DEFAULT {col_defaults[i]}'
                    column_defs.append(col_def)
            
            columns = ', '.join(column_defs)
        else:
            columns = request.POST.get('columns', '').strip()
        
        if not table_name or not columns:
            messages.error(request, 'Table name and columns are required.')
            return redirect('database_detail', db_name=db_name)
        
        try:
            sql = SQLiteManager.create_table(db_name, table_name, columns)
            QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Table "{table_name}" created successfully.')
        except Exception as e:
            QueryHistory.log_query(request.user, db_name, f'CREATE TABLE {table_name}', False, str(e))
            messages.error(request, f'Error creating table: {str(e)}')
        
        return redirect('database_detail', db_name=db_name)


class DropTableView(DatabaseWritePermissionMixin, View):
    """Requires write permission to drop tables."""
    def post(self, request, db_name, table_name):
        try:
            sql = SQLiteManager.drop_table(db_name, table_name)
            QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Table "{table_name}" dropped successfully.')
        except Exception as e:
            messages.error(request, f'Error dropping table: {str(e)}')
        
        return redirect('database_detail', db_name=db_name)


class TableDetailView(DatabaseReadPermissionMixin, TemplateView):
    """Requires read permission to view table details."""
    template_name = 'table/detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        db_name = kwargs['db_name']
        table_name = kwargs['table_name']
        user = self.request.user
        
        page = int(self.request.GET.get('page', 1))
        per_page = int(self.request.GET.get('per_page', 50))
        offset = (page - 1) * per_page
        
        columns = SQLiteManager.get_table_info(db_name, table_name)
        column_names = [col[1] for col in columns]
        
        rows = SQLiteManager.get_rows(db_name, table_name, per_page, offset)
        total_rows = SQLiteManager.get_row_count(db_name, table_name)
        total_pages = (total_rows + per_page - 1) // per_page
        
        indexes = SQLiteManager.get_table_indexes(db_name, table_name)
        
        # Determine user's permission level for UI display
        is_owner = DatabaseOwnership.is_owner(user, db_name)
        is_admin = user.is_superuser or user.is_staff
        can_write = is_owner or is_admin or DatabasePermission.has_write_permission(user, db_name)
        
        context['db_name'] = db_name
        context['table_name'] = table_name
        context['columns'] = columns
        context['column_names'] = column_names
        context['rows'] = rows
        context['indexes'] = indexes
        context['page'] = page
        context['per_page'] = per_page
        context['total_rows'] = total_rows
        context['total_pages'] = total_pages
        context['column_types'] = SQLiteManager.COLUMN_TYPES
        context['column_constraints'] = SQLiteManager.COLUMN_CONSTRAINTS
        context['can_write'] = can_write
        context['is_owner'] = is_owner
        context['is_admin'] = is_admin
        return context


class AddColumnView(DatabaseWritePermissionMixin, View):
    """Requires write permission to add columns."""
    def post(self, request, db_name, table_name):
        column_name = request.POST.get('column_name', '').strip()
        column_type = request.POST.get('column_type', '').strip()
        column_constraint = request.POST.get('column_constraint', '').strip()
        default_value = request.POST.get('default_value', '').strip()
        
        if not column_name or not column_type:
            messages.error(request, 'Column name and type are required.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        # Build full type with constraint
        full_type = column_type
        if column_constraint:
            full_type += f' {column_constraint}'
        
        try:
            sql = SQLiteManager.add_column(db_name, table_name, column_name, full_type, default_value or None)
            QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Column "{column_name}" added successfully.')
        except Exception as e:
            messages.error(request, f'Error adding column: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class DropColumnView(DatabaseWritePermissionMixin, View):
    """Requires write permission to drop columns."""
    def post(self, request, db_name, table_name, column_name):
        try:
            sql = SQLiteManager.drop_column(db_name, table_name, column_name)
            QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Column "{column_name}" dropped successfully.')
        except Exception as e:
            messages.error(request, f'Error dropping column: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class ModifyColumnView(DatabaseWritePermissionMixin, View):
    """Modify a column's type in a table. Requires write permission."""
    def post(self, request, db_name, table_name, column_name):
        new_type = request.POST.get('new_type', '').strip()
        new_constraint = request.POST.get('new_constraint', '').strip()
        
        if not new_type:
            messages.error(request, 'Column type is required.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        try:
            result = SQLiteManager.modify_column(db_name, table_name, column_name, new_type, new_constraint)
            QueryHistory.log_query(request.user, db_name, result)
            messages.success(request, f'Column "{column_name}" modified to {new_type} successfully.')
        except Exception as e:
            messages.error(request, f'Error modifying column: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class BulkAddColumnsView(DatabaseWritePermissionMixin, View):
    """Add multiple columns to a table at once. Requires write permission."""
    def post(self, request, db_name, table_name):
        col_names = request.POST.getlist('col_name[]')
        col_types = request.POST.getlist('col_type[]')
        col_constraints = request.POST.getlist('col_constraint[]')
        col_defaults = request.POST.getlist('col_default[]')
        
        columns = []
        for i, name in enumerate(col_names):
            if name.strip():
                columns.append({
                    'name': name.strip(),
                    'type': col_types[i] if i < len(col_types) else 'TEXT',
                    'constraint': col_constraints[i] if i < len(col_constraints) else '',
                    'default': col_defaults[i] if i < len(col_defaults) else ''
                })
        
        if not columns:
            messages.error(request, 'At least one column is required.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        try:
            sql_statements = SQLiteManager.add_columns_bulk(db_name, table_name, columns)
            for sql in sql_statements:
                QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Successfully added {len(sql_statements)} column(s).')
        except Exception as e:
            messages.error(request, f'Error adding columns: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class BulkDropColumnsView(DatabaseWritePermissionMixin, View):
    """Drop multiple columns from a table at once. Requires write permission."""
    def post(self, request, db_name, table_name):
        column_names = request.POST.getlist('columns[]')
        
        if not column_names:
            messages.error(request, 'No columns selected.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        try:
            sql_statements = SQLiteManager.drop_columns_bulk(db_name, table_name, column_names)
            for sql in sql_statements:
                QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Successfully dropped {len(sql_statements)} column(s).')
        except Exception as e:
            messages.error(request, f'Error dropping columns: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class CreateIndexView(DatabaseWritePermissionMixin, View):
    """Requires write permission to create indexes."""
    def post(self, request, db_name, table_name):
        index_name = request.POST.get('index_name', '').strip()
        # Support both checkbox list and comma-separated input
        index_columns = request.POST.getlist('index_columns')
        if not index_columns:
            columns = request.POST.get('columns', '').strip()
        else:
            columns = ', '.join(index_columns)
        unique = request.POST.get('unique', False) == 'on'
        
        if not index_name or not columns:
            messages.error(request, 'Index name and columns are required.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        try:
            sql = SQLiteManager.create_index(db_name, table_name, index_name, columns, unique)
            QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Index "{index_name}" created successfully.')
        except Exception as e:
            messages.error(request, f'Error creating index: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class DropIndexView(DatabaseWritePermissionMixin, View):
    """Requires write permission to drop indexes."""
    def post(self, request, db_name, table_name, index_name):
        try:
            sql = SQLiteManager.drop_index(db_name, index_name)
            QueryHistory.log_query(request.user, db_name, sql)
            messages.success(request, f'Index "{index_name}" dropped successfully.')
        except Exception as e:
            messages.error(request, f'Error dropping index: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


# Row Operations
class InsertRowView(DatabaseWritePermissionMixin, View):
    """Requires write permission to insert rows."""
    def get(self, request, db_name, table_name):
        columns = SQLiteManager.get_table_info(db_name, table_name)
        return render(request, 'table/insert_row.html', {
            'db_name': db_name,
            'table_name': table_name,
            'columns': columns
        })
    
    def post(self, request, db_name, table_name):
        columns = SQLiteManager.get_table_info(db_name, table_name)
        column_names = [col[1] for col in columns]
        
        values = []
        for col in column_names:
            val = request.POST.get(col, '')
            values.append(val if val else None)
        
        try:
            sql = SQLiteManager.insert_row(db_name, table_name, column_names, values)
            QueryHistory.log_query(request.user, db_name, f'{sql} with values {values}')
            messages.success(request, 'Row inserted successfully.')
        except Exception as e:
            messages.error(request, f'Error inserting row: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class UpdateRowView(DatabaseWritePermissionMixin, View):
    """Requires write permission to update rows."""
    def get(self, request, db_name, table_name, rowid):
        columns = SQLiteManager.get_table_info(db_name, table_name)
        column_names = [col[1] for col in columns]
        
        row = SQLiteManager.get_row_by_rowid(db_name, table_name, rowid)
        
        if not row:
            messages.error(request, 'Row not found.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        row_data = dict(zip(['rowid'] + column_names, row))
        
        return render(request, 'table/update_row.html', {
            'db_name': db_name,
            'table_name': table_name,
            'columns': columns,
            'row': row_data,
            'rowid': rowid
        })
    
    def post(self, request, db_name, table_name, rowid):
        columns = SQLiteManager.get_table_info(db_name, table_name)
        column_names = [col[1] for col in columns]
        
        values = []
        for col in column_names:
            val = request.POST.get(col, '')
            values.append(val if val else None)
        
        try:
            sql = SQLiteManager.update_row(db_name, table_name, column_names, values, rowid)
            QueryHistory.log_query(request.user, db_name, f'{sql} with values {values}')
            messages.success(request, 'Row updated successfully.')
        except Exception as e:
            messages.error(request, f'Error updating row: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class DeleteRowView(DatabaseWritePermissionMixin, View):
    """Requires write permission to delete rows."""
    def post(self, request, db_name, table_name, rowid):
        try:
            sql = SQLiteManager.delete_row(db_name, table_name, rowid)
            QueryHistory.log_query(request.user, db_name, f'{sql} with rowid={rowid}')
            messages.success(request, 'Row deleted successfully.')
        except Exception as e:
            messages.error(request, f'Error deleting row: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


# Export Views
class ExportTableView(DatabaseReadPermissionMixin, View):
    """Requires read permission to export table data."""
    def get(self, request, db_name, table_name):
        content = SQLiteManager.export_table_csv(db_name, table_name)
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{table_name}.csv"'
        return response


# Import Views
class ImportPreviewView(DatabaseWritePermissionMixin, View):
    """Preview import file and detect missing columns. Requires write permission."""
    def post(self, request, db_name, table_name):
        file = request.FILES.get('file')
        if not file:
            messages.error(request, 'No file uploaded.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        try:
            content = file.read().decode('utf-8')
            
            # Get columns from file
            if not file.name.endswith('.csv'):
                messages.error(request, 'Unsupported file format. Use CSV.')
                return redirect('table_detail', db_name=db_name, table_name=table_name)
            
            file_columns = SQLiteManager.get_csv_columns(content)
            
            # Get current table columns
            table_columns_info = SQLiteManager.get_table_info(db_name, table_name)
            table_columns = [col[1] for col in table_columns_info]
            
            # Find missing columns
            missing_columns = [col for col in file_columns if col not in table_columns]
            
            if missing_columns:
                # Store file content in session for later import
                request.session['import_file_content'] = content
                request.session['import_file_name'] = file.name
                
                return render(request, 'table/import_preview.html', {
                    'db_name': db_name,
                    'table_name': table_name,
                    'file_columns': file_columns,
                    'table_columns': table_columns,
                    'missing_columns': missing_columns,
                    'column_types': SQLiteManager.COLUMN_TYPES,
                    'column_constraints': SQLiteManager.COLUMN_CONSTRAINTS,
                })
            else:
                # No missing columns, proceed with import
                count = SQLiteManager.import_csv(db_name, table_name, content)
                
                if count > 0:
                    messages.success(request, f'Successfully imported {count} rows.')
                else:
                    messages.warning(request, 'No data to import.')
                    
        except Exception as e:
            messages.error(request, f'Error processing file: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class ImportWithColumnsView(DatabaseWritePermissionMixin, View):
    """Add missing columns and then import data. Requires write permission."""
    def post(self, request, db_name, table_name):
        action = request.POST.get('action', 'import_all')
        
        # Get stored file content
        content = request.session.get('import_file_content')
        file_name = request.session.get('import_file_name', '')
        
        if not content:
            messages.error(request, 'Import session expired. Please upload the file again.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        try:
            if action == 'add_columns':
                # Add selected columns first
                col_names = request.POST.getlist('col_name[]')
                col_types = request.POST.getlist('col_type[]')
                col_constraints = request.POST.getlist('col_constraint[]')
                col_defaults = request.POST.getlist('col_default[]')
                
                columns = []
                for i, name in enumerate(col_names):
                    if name.strip():
                        columns.append({
                            'name': name.strip(),
                            'type': col_types[i] if i < len(col_types) else 'TEXT',
                            'constraint': col_constraints[i] if i < len(col_constraints) else '',
                            'default': col_defaults[i] if i < len(col_defaults) else ''
                        })
                
                if columns:
                    sql_statements = SQLiteManager.add_columns_bulk(db_name, table_name, columns)
                    for sql in sql_statements:
                        QueryHistory.log_query(request.user, db_name, sql)
                    messages.success(request, f'Added {len(sql_statements)} column(s).')
            
            # Now import the data
            count = SQLiteManager.import_csv(db_name, table_name, content)
            
            if count > 0:
                messages.success(request, f'Successfully imported {count} rows.')
            else:
                messages.warning(request, 'No data to import.')
                
        except Exception as e:
            messages.error(request, f'Error importing data: {str(e)}')
        finally:
            # Clear session data
            request.session.pop('import_file_content', None)
            request.session.pop('import_file_name', None)
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


class ImportDataView(DatabaseWritePermissionMixin, View):
    """Requires write permission to import data."""
    def post(self, request, db_name, table_name):
        file = request.FILES.get('file')
        if not file:
            messages.error(request, 'No file uploaded.')
            return redirect('table_detail', db_name=db_name, table_name=table_name)
        
        try:
            content = file.read().decode('utf-8')
            
            if not file.name.endswith('.csv'):
                messages.error(request, 'Unsupported file format. Use CSV.')
                return redirect('table_detail', db_name=db_name, table_name=table_name)
            
            count = SQLiteManager.import_csv(db_name, table_name, content)
            
            if count > 0:
                messages.success(request, f'Successfully imported {count} rows.')
            else:
                messages.warning(request, 'No data to import.')
        except Exception as e:
            messages.error(request, f'Error importing data: {str(e)}')
        
        return redirect('table_detail', db_name=db_name, table_name=table_name)


# Query Execution
class ExecuteQueryView(DatabaseReadPermissionMixin, View):
    """Execute SQL queries. Read permission required, write operations check additional permission."""
    def post(self, request, db_name):
        query = request.POST.get('query', '').strip()
        
        if not query:
            return JsonResponse({'error': 'No query provided'}, status=400)
        
        # Check if query modifies data (requires write permission)
        query_upper = query.upper().strip()
        is_write_query = any(query_upper.startswith(cmd) for cmd in [
            'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE'
        ])
        
        if is_write_query:
            can_write, reason = DatabasePermissionChecker.can_access_database(
                request.user, db_name, require_write=True
            )
            if not can_write:
                return JsonResponse({'error': f'Write permission denied: {reason}'}, status=403)
        
        try:
            result = SQLiteManager.execute_query(db_name, query)
            QueryHistory.log_query(request.user, db_name, query)
            
            if result['type'] == 'select':
                return JsonResponse({
                    'success': True,
                    'columns': result['columns'],
                    'rows': result['rows'],
                    'row_count': result['row_count']
                })
            else:
                return JsonResponse({
                    'success': True,
                    'message': f'Query executed successfully. {result["affected_rows"]} row(s) affected.',
                    'affected_rows': result['affected_rows']
                })
                
        except Exception as e:
            QueryHistory.log_query(request.user, db_name, query, False, str(e))
            return JsonResponse({'error': str(e)}, status=400)


class QueryHistoryView(LoginRequiredMixin, TemplateView):
    template_name = 'database/query_history.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        db_name = kwargs.get('db_name')
        
        history = QueryHistory.objects.filter(user=self.request.user)
        if db_name:
            history = history.filter(database_name=db_name)
        
        context['history'] = history[:100]
        context['db_name'] = db_name
        
        formatter = HtmlFormatter(style='friendly')
        context['pygments_css'] = formatter.get_style_defs('.highlight')
        
        highlighted_history = []
        for h in context['history']:
            highlighted = highlight(h.query, SqlLexer(), formatter)
            highlighted_history.append({
                'id': h.id,
                'query': h.query,
                'highlighted_query': highlighted,
                'executed_at': h.executed_at,
                'success': h.success,
                'error_message': h.error_message,
                'database_name': h.database_name
            })
        context['highlighted_history'] = highlighted_history
        
        return context


# Table Schema View
class TableSchemaView(DatabaseReadPermissionMixin, View):
    """Requires read permission to view table schema."""
    def get(self, request, db_name, table_name):
        try:
            sql = SQLiteManager.get_table_schema(db_name, table_name)
            
            if sql:
                formatter = HtmlFormatter(style='friendly')
                highlighted = highlight(sql, SqlLexer(), formatter)
                return JsonResponse({
                    'success': True,
                    'sql': sql,
                    'highlighted': highlighted,
                    'css': formatter.get_style_defs('.highlight')
                })
            else:
                return JsonResponse({'error': 'Table not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


# Dashboard Views
class DashboardListView(LoginRequiredMixin, TemplateView):
    """List all dashboards for a user."""
    template_name = 'dashboard/list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dashboards'] = Dashboard.objects.filter(user=self.request.user)
        return context


class CreateDashboardView(LoginRequiredMixin, View):
    """Create a new dashboard."""
    def post(self, request):
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        
        if not name:
            messages.error(request, 'Dashboard name is required.')
            return redirect('dashboard_list')
        
        try:
            Dashboard.objects.create(
                user=request.user,
                name=name,
                description=description
            )
            messages.success(request, f'Dashboard "{name}" created successfully.')
        except Exception as e:
            if 'UNIQUE constraint' in str(e):
                messages.error(request, f'A dashboard named "{name}" already exists.')
            else:
                messages.error(request, f'Error creating dashboard: {str(e)}')
        
        return redirect('dashboard_list')


class EditDashboardView(LoginRequiredMixin, View):
    """Edit a dashboard."""
    def get(self, request, dashboard_id):
        dashboard = Dashboard.objects.filter(id=dashboard_id, user=request.user).first()
        if not dashboard:
            messages.error(request, 'Dashboard not found.')
            return redirect('dashboard_list')
        
        return render(request, 'dashboard/edit_dashboard.html', {
            'dashboard': dashboard
        })
    
    def post(self, request, dashboard_id):
        dashboard = Dashboard.objects.filter(id=dashboard_id, user=request.user).first()
        if not dashboard:
            messages.error(request, 'Dashboard not found.')
            return redirect('dashboard_list')
        
        dashboard.name = request.POST.get('name', '').strip()
        dashboard.description = request.POST.get('description', '').strip()
        
        if not dashboard.name:
            messages.error(request, 'Dashboard name is required.')
            return redirect('edit_dashboard', dashboard_id=dashboard_id)
        
        try:
            dashboard.save()
            messages.success(request, f'Dashboard "{dashboard.name}" updated successfully.')
        except Exception as e:
            if 'UNIQUE constraint' in str(e):
                messages.error(request, f'A dashboard named "{dashboard.name}" already exists.')
            else:
                messages.error(request, f'Error updating dashboard: {str(e)}')
        
        return redirect('dashboard_list')


class DeleteDashboardView(LoginRequiredMixin, View):
    """Delete a dashboard."""
    def post(self, request, dashboard_id):
        dashboard = Dashboard.objects.filter(id=dashboard_id, user=request.user).first()
        if dashboard:
            if dashboard.is_default:
                messages.error(request, 'Cannot delete the default dashboard.')
            else:
                name = dashboard.name
                # Move charts to default dashboard before deletion
                default_dashboard = Dashboard.get_or_create_default(request.user)
                dashboard.charts.update(dashboard=default_dashboard)
                dashboard.delete()
                messages.success(request, f'Dashboard "{name}" deleted. Charts moved to default dashboard.')
        else:
            messages.error(request, 'Dashboard not found.')
        return redirect('dashboard_list')


class SetDefaultDashboardView(LoginRequiredMixin, View):
    """Set a dashboard as the default."""
    def post(self, request, dashboard_id):
        dashboard = Dashboard.objects.filter(id=dashboard_id, user=request.user).first()
        if dashboard:
            dashboard.is_default = True
            dashboard.save()
            messages.success(request, f'"{dashboard.name}" is now your default dashboard.')
        else:
            messages.error(request, 'Dashboard not found.')
        return redirect('dashboard_list')


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard_id = kwargs.get('dashboard_id')
        
        if dashboard_id:
            dashboard = Dashboard.objects.filter(id=dashboard_id, user=self.request.user).first()
            if not dashboard:
                dashboard = Dashboard.get_or_create_default(self.request.user)
        else:
            dashboard = Dashboard.get_or_create_default(self.request.user)
        
        context['current_dashboard'] = dashboard
        context['dashboards'] = Dashboard.objects.filter(user=self.request.user)
        context['charts'] = DashboardChart.objects.filter(dashboard=dashboard)
        context['databases'] = SQLiteManager.list_databases()
        context['chart_types'] = DashboardChart.CHART_TYPES
        return context


class CreateChartView(LoginRequiredMixin, View):
    def get(self, request):
        dashboard_id = request.GET.get('dashboard')
        dashboard = None
        if dashboard_id:
            dashboard = Dashboard.objects.filter(id=dashboard_id, user=request.user).first()
        
        databases = SQLiteManager.list_databases()
        dashboards = Dashboard.objects.filter(user=request.user)
        return render(request, 'dashboard/create_chart.html', {
            'databases': databases,
            'chart_types': DashboardChart.CHART_TYPES,
            'refresh_choices': DashboardChart.REFRESH_CHOICES,
            'dashboards': dashboards,
            'selected_dashboard': dashboard,
        })
    
    def post(self, request):
        title = request.POST.get('title', '').strip()
        database_name = request.POST.get('database_name', '').strip()
        query = request.POST.get('query', '').strip()
        chart_type = request.POST.get('chart_type', 'bar')
        auto_refresh = int(request.POST.get('auto_refresh', 0))
        dashboard_id = request.POST.get('dashboard_id', '').strip()
        
        if not all([title, database_name, query]):
            messages.error(request, 'All fields are required.')
            return redirect('create_chart')
        
        try:
            dashboard = None
            if dashboard_id:
                dashboard = Dashboard.objects.filter(id=dashboard_id, user=request.user).first()
            if not dashboard:
                dashboard = Dashboard.get_or_create_default(request.user)
            
            chart = DashboardChart.objects.create(
                user=request.user,
                dashboard=dashboard,
                title=title,
                database_name=database_name,
                query=query,
                chart_type=chart_type,
                auto_refresh=auto_refresh
            )
            messages.success(request, f'Chart "{title}" created successfully.')
            return redirect('dashboard_detail', dashboard_id=dashboard.id)
        except Exception as e:
            messages.error(request, f'Error creating chart: {str(e)}')
            return redirect('create_chart')


class EditChartView(LoginRequiredMixin, View):
    def get(self, request, chart_id):
        chart = DashboardChart.objects.filter(id=chart_id, user=request.user).first()
        if not chart:
            messages.error(request, 'Chart not found.')
            return redirect('dashboard_list')
        
        databases = SQLiteManager.list_databases()
        dashboards = Dashboard.objects.filter(user=request.user)
        return render(request, 'dashboard/edit_chart.html', {
            'chart': chart,
            'databases': databases,
            'chart_types': DashboardChart.CHART_TYPES,
            'refresh_choices': DashboardChart.REFRESH_CHOICES,
            'dashboards': dashboards,
        })
    
    def post(self, request, chart_id):
        chart = DashboardChart.objects.filter(id=chart_id, user=request.user).first()
        if not chart:
            messages.error(request, 'Chart not found.')
            return redirect('dashboard_list')
        
        chart.title = request.POST.get('title', '').strip()
        chart.database_name = request.POST.get('database_name', '').strip()
        chart.query = request.POST.get('query', '').strip()
        chart.chart_type = request.POST.get('chart_type', 'bar')
        chart.auto_refresh = int(request.POST.get('auto_refresh', 0))
        dashboard_id = request.POST.get('dashboard_id', '').strip()
        
        if dashboard_id:
            dashboard = Dashboard.objects.filter(id=dashboard_id, user=request.user).first()
            if dashboard:
                chart.dashboard = dashboard
        
        if not all([chart.title, chart.database_name, chart.query]):
            messages.error(request, 'All fields are required.')
            return redirect('edit_chart', chart_id=chart_id)
        
        try:
            chart.save()
            messages.success(request, f'Chart "{chart.title}" updated successfully.')
            return redirect('dashboard_detail', dashboard_id=chart.dashboard.id)
        except Exception as e:
            messages.error(request, f'Error updating chart: {str(e)}')
            return redirect('edit_chart', chart_id=chart_id)


class DeleteChartView(LoginRequiredMixin, View):
    def post(self, request, chart_id):
        chart = DashboardChart.objects.filter(id=chart_id, user=request.user).first()
        if chart:
            title = chart.title
            dashboard_id = chart.dashboard.id if chart.dashboard else None
            chart.delete()
            messages.success(request, f'Chart "{title}" deleted.')
            if dashboard_id:
                return redirect('dashboard_detail', dashboard_id=dashboard_id)
        else:
            messages.error(request, 'Chart not found.')
        return redirect('dashboard_list')


class PreviewChartView(LoginRequiredMixin, View):
    """Preview chart data without saving."""
    def post(self, request):
        database_name = request.POST.get('database_name', '').strip()
        query = request.POST.get('query', '').strip()
        
        if not database_name or not query:
            return JsonResponse({'error': 'Database and query are required.'}, status=400)
        
        try:
            with SQLiteManager.get_connection(database_name, row_factory=True) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
                if rows:
                    columns = list(rows[0].keys())
                    data = [dict(row) for row in rows]
                    return JsonResponse({'success': True, 'columns': columns, 'data': data})
                return JsonResponse({'success': True, 'columns': [], 'data': []})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


class ChartDataView(LoginRequiredMixin, View):
    """Get chart data for rendering (used for refresh)."""
    def get(self, request, chart_id):
        chart = DashboardChart.objects.filter(id=chart_id, user=request.user).first()
        if not chart:
            return JsonResponse({'error': 'Chart not found.'}, status=404)
        
        result = chart.execute_query()
        if result['success']:
            return JsonResponse({
                'success': True,
                'title': chart.title,
                'chart_type': chart.chart_type,
                'auto_refresh': chart.auto_refresh,
                'columns': result['columns'],
                'data': result['data']
            })
        return JsonResponse({'error': result['error']}, status=400)


class DatabaseSchemaAPIView(DatabaseReadPermissionMixin, View):
    """Get all tables and their columns for a database (for chart query helper). Requires read permission."""
    def get(self, request, db_name):
        try:
            if not SQLiteManager.database_exists(db_name):
                return JsonResponse({'error': 'Database not found'}, status=404)
            
            tables = SQLiteManager.get_tables(db_name)
            schema = {}
            
            for table in tables:
                columns_info = SQLiteManager.get_table_info(db_name, table)
                schema[table] = [
                    {
                        'name': col[1],
                        'type': col[2],
                        'nullable': not col[3],
                        'pk': bool(col[5])
                    }
                    for col in columns_info
                ]
            
            return JsonResponse({
                'success': True,
                'database': db_name,
                'tables': schema
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


# Permission Management Views
class DatabasePermissionsView(DatabaseOwnerOrAdminMixin, TemplateView):
    """View and manage database permissions. Only owners and admins can access."""
    template_name = 'database/permissions.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        db_name = kwargs['db_name']
        
        # Get current permissions
        permissions = DatabasePermission.get_shared_users(db_name)
        
        # Get ownership info
        owner = DatabaseOwnership.get_owner(db_name)
        
        # Get all users for the dropdown (exclude owner and already shared users)
        shared_user_ids = [p.granted_to.id for p in permissions]
        if owner:
            shared_user_ids.append(owner.id)
        available_users = User.objects.exclude(id__in=shared_user_ids).order_by('username')
        
        context['db_name'] = db_name
        context['permissions'] = permissions
        context['owner'] = owner
        context['available_users'] = available_users
        context['permission_choices'] = DatabasePermission.PERMISSION_CHOICES
        context['is_owner'] = owner == self.request.user if owner else False
        context['is_admin'] = self.request.user.is_superuser or self.request.user.is_staff
        return context


class GrantPermissionView(DatabaseOwnerOrAdminMixin, View):
    """Grant permission to a user for a database."""
    def post(self, request, db_name):
        user_id = request.POST.get('user_id')
        permission_level = request.POST.get('permission_level', 'read')
        
        if not user_id:
            messages.error(request, 'Please select a user.')
            return redirect('database_permissions', db_name=db_name)
        
        try:
            user = User.objects.get(id=user_id)
            
            # Check if user is the owner (can't grant permission to owner)
            if DatabaseOwnership.is_owner(user, db_name):
                messages.error(request, 'Cannot grant permission to the database owner.')
                return redirect('database_permissions', db_name=db_name)
            
            DatabasePermission.grant_permission(
                database_name=db_name,
                granted_by=request.user,
                granted_to=user,
                permission_level=permission_level
            )
            messages.success(request, f'Permission granted to {user.username}.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        except Exception as e:
            messages.error(request, f'Error granting permission: {str(e)}')
        
        return redirect('database_permissions', db_name=db_name)


class UpdatePermissionView(DatabaseOwnerOrAdminMixin, View):
    """Update a user's permission level."""
    def post(self, request, db_name, user_id):
        permission_level = request.POST.get('permission_level', 'read')
        
        try:
            user = User.objects.get(id=user_id)
            perm = DatabasePermission.objects.get(database_name=db_name, granted_to=user)
            perm.permission_level = permission_level
            perm.save()
            messages.success(request, f'Permission updated for {user.username}.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        except DatabasePermission.DoesNotExist:
            messages.error(request, 'Permission not found.')
        except Exception as e:
            messages.error(request, f'Error updating permission: {str(e)}')
        
        return redirect('database_permissions', db_name=db_name)


class RevokePermissionView(DatabaseOwnerOrAdminMixin, View):
    """Revoke a user's permission for a database."""
    def post(self, request, db_name, user_id):
        try:
            user = User.objects.get(id=user_id)
            deleted, _ = DatabasePermission.revoke_permission(db_name, user)
            if deleted:
                messages.success(request, f'Permission revoked for {user.username}.')
            else:
                messages.warning(request, 'No permission found to revoke.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        except Exception as e:
            messages.error(request, f'Error revoking permission: {str(e)}')
        
        return redirect('database_permissions', db_name=db_name)


class TransferOwnershipView(DatabaseOwnerOrAdminMixin, View):
    """Transfer database ownership to another user. Only current owner or admin can do this."""
    def post(self, request, db_name):
        new_owner_id = request.POST.get('new_owner_id')
        
        if not new_owner_id:
            messages.error(request, 'Please select a new owner.')
            return redirect('database_permissions', db_name=db_name)
        
        try:
            new_owner = User.objects.get(id=new_owner_id)
            current_owner = DatabaseOwnership.get_owner(db_name)
            
            # Only the current owner or a superuser can transfer ownership
            if current_owner != request.user and not request.user.is_superuser:
                messages.error(request, 'Only the current owner or a superuser can transfer ownership.')
                return redirect('database_permissions', db_name=db_name)
            
            # Transfer ownership
            if DatabaseOwnership.transfer_ownership(db_name, new_owner):
                # Remove any existing permission for the new owner (they're now the owner)
                DatabasePermission.revoke_permission(db_name, new_owner)
                messages.success(request, f'Ownership transferred to {new_owner.username}.')
            else:
                messages.error(request, 'Failed to transfer ownership.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        except Exception as e:
            messages.error(request, f'Error transferring ownership: {str(e)}')
        
        return redirect('database_permissions', db_name=db_name)


class ToggleAPIView(LoginRequiredMixin, View):
    def post(self, request, db_name):
        try:
            ownership = DatabaseOwnership.objects.get(database_name=db_name)
            if ownership.owner != request.user and not request.user.is_superuser:
                messages.error(request, 'Permission denied.')
                return redirect('database_detail', db_name=db_name)
            
            api_enabled = request.POST.get('api_enabled') == 'on'
            ownership.api_enabled = api_enabled
            if api_enabled and not ownership.api_secret_key:
                ownership.generate_api_key()
            ownership.save()
            
            status = "enabled" if api_enabled else "disabled"
            messages.success(request, f'API access {status}.')
        except DatabaseOwnership.DoesNotExist:
            messages.error(request, 'Database not found.')
            
        return redirect('database_detail', db_name=db_name)


class RegenerateAPIKeyView(LoginRequiredMixin, View):
    def post(self, request, db_name):
        try:
            ownership = DatabaseOwnership.objects.get(database_name=db_name)
            if ownership.owner != request.user and not request.user.is_superuser:
                messages.error(request, 'Permission denied.')
                return redirect('database_detail', db_name=db_name)
            
            ownership.generate_api_key()
            messages.success(request, 'API Key regenerated.')
        except DatabaseOwnership.DoesNotExist:
            messages.error(request, 'Database not found.')
            
        return redirect('database_detail', db_name=db_name)


class ClaimOwnershipView(LoginRequiredMixin, View):
    """Allow admins or staff to claim ownership of legacy databases."""
    def post(self, request, db_name):
        user = request.user
        
        # Only superusers/staff can claim legacy databases
        if not (user.is_superuser or user.is_staff):
            messages.error(request, 'Only administrators can claim legacy databases.')
            return redirect('database_detail', db_name=db_name)
        
        success, message = DatabaseOwnership.claim_ownership(user, db_name)
        if success:
            messages.success(request, f'You are now the owner of "{db_name}".')
        else:
            messages.error(request, message)
        
        return redirect('database_detail', db_name=db_name)

