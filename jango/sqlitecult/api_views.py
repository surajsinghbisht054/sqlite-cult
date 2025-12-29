"""
REST API views for SQLite Cult.
Provides CRUD operations for database tables via API.
Uses JWT tokens for authentication with embedded permissions.
"""
import json
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import SqliteFile, SQLiteManager
from .services import RowService
from .responses import APIResponse
from .constants import (
    ErrorMessages, DEFAULT_PAGE_SIZE,
    API_PERMISSION_READ, API_PERMISSION_CREATE,
    API_PERMISSION_UPDATE, API_PERMISSION_DELETE
)
from .jwt_utils import JWTManager, extract_token_from_header


class JWTAuthMixin:
    """
    Mixin for API authentication using JWT tokens.
    Validates the Authorization header and extracts permissions.
    """
    
    # Override in subclasses to require specific permissions
    required_permission = None
    
    def dispatch(self, request, *args, **kwargs):
        self.db_name = kwargs.get('db_name')
        
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        token = extract_token_from_header(auth_header)
        
        if not token:
            return APIResponse.unauthorized(ErrorMessages.JWT_MISSING)
        
        # Decode and validate token
        payload, error = JWTManager.decode_token(token)
        
        if error:
            if 'expired' in error.lower():
                return APIResponse.unauthorized(ErrorMessages.JWT_EXPIRED)
            return APIResponse.unauthorized(ErrorMessages.JWT_INVALID)
        
        # Get the SqliteFile and verify token matches
        sqlite_file = SqliteFile.get_by_actual_filename(self.db_name)
        
        if not sqlite_file:
            return APIResponse.not_found(ErrorMessages.DATABASE_NOT_FOUND)
        
        if not sqlite_file.api_enabled:
            return APIResponse.forbidden(ErrorMessages.API_DISABLED)
        
        # Verify the token belongs to this database
        if payload.get('sqlite_file_id') != sqlite_file.id:
            return APIResponse.unauthorized(ErrorMessages.JWT_INVALID)
        
        # Check required permission if specified
        if self.required_permission:
            if not JWTManager.has_permission(payload, self.required_permission):
                return APIResponse.forbidden(ErrorMessages.API_PERMISSION_DENIED)
        
        # Store sqlite_file and permissions for use in views
        self.sqlite_file = sqlite_file
        self.jwt_payload = payload
        self.api_permissions = payload.get('permissions', [])
        
        return super().dispatch(request, *args, **kwargs)
    
    def has_permission(self, permission):
        """Check if the current token has a specific permission."""
        return JWTManager.has_permission(self.jwt_payload, permission)


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
class APITableListView(JWTAuthMixin, BaseAPIView):
    """
    List all tables in a database.
    
    GET /api/v1/database/{db_name}/tables/
    Requires: read permission
    """
    required_permission = API_PERMISSION_READ
    
    def get(self, request, db_name):
        try:
            tables = SQLiteManager.get_tables(db_name)
            return APIResponse.success({'tables': tables})
        except Exception as e:
            return APIResponse.server_error(str(e))


@method_decorator(csrf_exempt, name='dispatch')
class APITableDataView(JWTAuthMixin, BaseAPIView):
    """
    List rows or create a new row in a table.
    
    GET /api/v1/database/{db_name}/table/{table_name}/
        Query params: limit (default 50), offset (default 0)
        Requires: read permission
        
    POST /api/v1/database/{db_name}/table/{table_name}/
        Body: JSON object with column values
        Requires: create permission
    """
    
    def get(self, request, db_name, table_name):
        # Check read permission
        if not self.has_permission(API_PERMISSION_READ):
            return APIResponse.forbidden(ErrorMessages.API_PERMISSION_DENIED)
        
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
        # Check create permission
        if not self.has_permission(API_PERMISSION_CREATE):
            return APIResponse.forbidden(ErrorMessages.API_PERMISSION_DENIED)
        
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
class APIRowDetailView(JWTAuthMixin, BaseAPIView):
    """
    Get, update, or delete a specific row.
    
    GET /api/v1/database/{db_name}/table/{table_name}/{rowid}/
        Requires: read permission
    PUT /api/v1/database/{db_name}/table/{table_name}/{rowid}/
        Requires: update permission
    DELETE /api/v1/database/{db_name}/table/{table_name}/{rowid}/
        Requires: delete permission
    """
    
    def get(self, request, db_name, table_name, rowid):
        # Check read permission
        if not self.has_permission(API_PERMISSION_READ):
            return APIResponse.forbidden(ErrorMessages.API_PERMISSION_DENIED)
        
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
        # Check update permission
        if not self.has_permission(API_PERMISSION_UPDATE):
            return APIResponse.forbidden(ErrorMessages.API_PERMISSION_DENIED)
        
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
        # Check delete permission
        if not self.has_permission(API_PERMISSION_DELETE):
            return APIResponse.forbidden(ErrorMessages.API_PERMISSION_DENIED)
        
        try:
            SQLiteManager.delete_row(db_name, table_name, rowid)
            return APIResponse.success(message='Row deleted')
        except Exception as e:
            return APIResponse.server_error(str(e))
