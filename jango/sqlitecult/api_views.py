"""
REST API views for SQLite Cult.
Provides CRUD operations for database tables via API.
"""
import json
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import DatabaseOwnership, SQLiteManager
from .services import RowService
from .responses import APIResponse
from .constants import ErrorMessages, DEFAULT_PAGE_SIZE


class APIAuthMixin:
    """
    Mixin for API authentication using API keys.
    Validates the X-API-Key header against the database's API key.
    """
    
    def dispatch(self, request, *args, **kwargs):
        self.db_name = kwargs.get('db_name')
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return APIResponse.unauthorized(ErrorMessages.MISSING_API_KEY)
        
        try:
            ownership = DatabaseOwnership.objects.get(database_name=self.db_name)
            if not ownership.api_enabled:
                return APIResponse.forbidden(ErrorMessages.API_DISABLED)
            
            if ownership.api_secret_key != api_key:
                return APIResponse.unauthorized(ErrorMessages.INVALID_API_KEY)
                
        except DatabaseOwnership.DoesNotExist:
            return APIResponse.not_found(ErrorMessages.DATABASE_NOT_FOUND)
        
        return super().dispatch(request, *args, **kwargs)


class BaseAPIView(View):
    """
    Base class for API views with common utilities.
    """
    
    def get_table_columns(self, db_name, table_name):
        """Get column names for a table."""
        columns_info = SQLiteManager.get_table_info(db_name, table_name)
        return [col[1] for col in columns_info]
    
    def parse_json_body(self, request):
        """
        Parse JSON from request body.
        
        Returns:
            tuple: (data, error_response) - error_response is None if successful
        """
        try:
            return json.loads(request.body), None
        except json.JSONDecodeError:
            return None, APIResponse.bad_request('Invalid JSON')
    
    def validate_columns(self, data, valid_columns):
        """
        Validate and extract columns from request data.
        
        Returns:
            tuple: (columns, values) - lists of valid columns and their values
        """
        columns = []
        values = []
        for col, val in data.items():
            if col in valid_columns:
                columns.append(col)
                values.append(val)
        return columns, values


@method_decorator(csrf_exempt, name='dispatch')
class APITableListView(APIAuthMixin, BaseAPIView):
    """
    List all tables in a database.
    
    GET /api/v1/database/{db_name}/tables/
    """
    
    def get(self, request, db_name):
        try:
            tables = SQLiteManager.get_tables(db_name)
            return APIResponse.success({'tables': tables})
        except Exception as e:
            return APIResponse.server_error(str(e))


@method_decorator(csrf_exempt, name='dispatch')
class APITableDataView(APIAuthMixin, BaseAPIView):
    """
    List rows or create a new row in a table.
    
    GET /api/v1/database/{db_name}/table/{table_name}/
        Query params: limit (default 50), offset (default 0)
        
    POST /api/v1/database/{db_name}/table/{table_name}/
        Body: JSON object with column values
    """
    
    def get(self, request, db_name, table_name):
        # Parse pagination parameters
        try:
            limit = int(request.GET.get('limit', DEFAULT_PAGE_SIZE))
            offset = int(request.GET.get('offset', 0))
        except ValueError:
            return APIResponse.bad_request('Invalid limit or offset')
        
        try:
            rows = SQLiteManager.get_rows(db_name, table_name, limit, offset)
            columns = self.get_table_columns(db_name, table_name)
            data = RowService.serialize_rows(rows, columns)
            
            return APIResponse.paginated(data, columns, len(data), limit, offset)
        except Exception as e:
            return APIResponse.server_error(str(e))

    def post(self, request, db_name, table_name):
        data, error = self.parse_json_body(request)
        if error:
            return error
        
        try:
            valid_columns = self.get_table_columns(db_name, table_name)
            insert_columns, insert_values = self.validate_columns(data, valid_columns)
            
            if not insert_columns:
                return APIResponse.bad_request('No valid columns provided')
            
            SQLiteManager.insert_row(db_name, table_name, insert_columns, insert_values)
            return APIResponse.created(message='Row created')
        except Exception as e:
            return APIResponse.server_error(str(e))


@method_decorator(csrf_exempt, name='dispatch')
class APIRowDetailView(APIAuthMixin, BaseAPIView):
    """
    Get, update, or delete a specific row.
    
    GET /api/v1/database/{db_name}/table/{table_name}/{rowid}/
    PUT /api/v1/database/{db_name}/table/{table_name}/{rowid}/
    DELETE /api/v1/database/{db_name}/table/{table_name}/{rowid}/
    """
    
    def get(self, request, db_name, table_name, rowid):
        try:
            row = SQLiteManager.get_row_by_rowid(db_name, table_name, rowid)
            if not row:
                return APIResponse.not_found(ErrorMessages.ROW_NOT_FOUND)
            
            columns = self.get_table_columns(db_name, table_name)
            row_dict = RowService.serialize_row(row, columns)
            
            return APIResponse.success(row_dict)
        except Exception as e:
            return APIResponse.server_error(str(e))

    def put(self, request, db_name, table_name, rowid):
        data, error = self.parse_json_body(request)
        if error:
            return error
        
        try:
            valid_columns = self.get_table_columns(db_name, table_name)
            update_columns, update_values = self.validate_columns(data, valid_columns)
            
            if not update_columns:
                return APIResponse.bad_request('No valid columns provided')
            
            SQLiteManager.update_row(db_name, table_name, update_columns, update_values, rowid)
            return APIResponse.success(message='Row updated')
        except Exception as e:
            return APIResponse.server_error(str(e))

    def delete(self, request, db_name, table_name, rowid):
        try:
            SQLiteManager.delete_row(db_name, table_name, rowid)
            return APIResponse.success(message='Row deleted')
        except Exception as e:
            return APIResponse.server_error(str(e))
