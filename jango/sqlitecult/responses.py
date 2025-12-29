"""
Response helpers for consistent API responses.
Provides standardized JSON response formatting.
"""
from django.http import JsonResponse
from .constants import ErrorMessages


class APIResponse:
    """
    Helper class for creating consistent API responses.
    """
    
    @staticmethod
    def success(data=None, message=None, status=200):
        """Create a success response."""
        response = {'success': True}
        if message:
            response['message'] = message
        if data:
            response.update(data)
        return JsonResponse(response, status=status)
    
    @staticmethod
    def created(data=None, message='Created successfully'):
        """Create a 201 Created response."""
        return APIResponse.success(data, message, status=201)
    
    @staticmethod
    def error(message, status=400, code=None):
        """Create an error response."""
        response = {'success': False, 'error': message}
        if code:
            response['code'] = code
        return JsonResponse(response, status=status)
    
    @staticmethod
    def not_found(message=None):
        """Create a 404 Not Found response."""
        return APIResponse.error(message or ErrorMessages.ROW_NOT_FOUND, status=404)
    
    @staticmethod
    def forbidden(message=None):
        """Create a 403 Forbidden response."""
        return APIResponse.error(message or ErrorMessages.PERMISSION_DENIED, status=403)
    
    @staticmethod
    def unauthorized(message=None):
        """Create a 401 Unauthorized response."""
        return APIResponse.error(message or ErrorMessages.INVALID_API_KEY, status=401)
    
    @staticmethod
    def server_error(message=None):
        """Create a 500 Internal Server Error response."""
        return APIResponse.error(message or 'Internal server error', status=500)
    
    @staticmethod
    def bad_request(message=None):
        """Create a 400 Bad Request response."""
        return APIResponse.error(message or ErrorMessages.INVALID_INPUT, status=400)
    
    @staticmethod
    def query_result(result):
        """
        Create a response for query execution results.
        
        Args:
            result: dict with 'type', 'columns', 'rows', 'row_count' or 'affected_rows'
        """
        if result['type'] == 'select':
            return APIResponse.success({
                'columns': result['columns'],
                'rows': result['rows'],
                'row_count': result['row_count']
            })
        else:
            return APIResponse.success(
                data={'affected_rows': result['affected_rows']},
                message=f"Query executed successfully. {result['affected_rows']} row(s) affected."
            )
    
    @staticmethod
    def paginated(data, columns, count, limit, offset):
        """
        Create a paginated response.
        """
        return APIResponse.success({
            'columns': columns,
            'data': data,
            'count': count,
            'limit': limit,
            'offset': offset,
        })
