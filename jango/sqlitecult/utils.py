"""
Utility functions for SQLite Cult application.
Contains common helper functions used across the application.
"""
from functools import wraps
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import redirect


def json_error(message, status=400):
    """
    Return a JSON error response.
    
    Args:
        message: Error message
        status: HTTP status code
    
    Returns:
        JsonResponse with error
    """
    return JsonResponse({'error': message}, status=status)


def json_success(data=None, message=None, status=200):
    """
    Return a JSON success response.
    
    Args:
        data: Optional data dict
        message: Optional success message
        status: HTTP status code
    
    Returns:
        JsonResponse with success
    """
    response = {'success': True}
    if data:
        response.update(data)
    if message:
        response['message'] = message
    return JsonResponse(response, status=status)


def is_ajax_request(request):
    """
    Check if request is an AJAX request.
    
    Args:
        request: HTTP request object
    
    Returns:
        bool: True if AJAX request
    """
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def get_or_none(model, **kwargs):
    """
    Get a model instance or None if not found.
    
    Args:
        model: Django model class
        **kwargs: Filter arguments
    
    Returns:
        Model instance or None
    """
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        return None


def get_pagination_params(request, default_per_page=50):
    """
    Extract pagination parameters from request.
    
    Args:
        request: HTTP request object
        default_per_page: Default items per page
    
    Returns:
        tuple: (page, per_page, offset)
    """
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', default_per_page))
    except (TypeError, ValueError):
        page = 1
        per_page = default_per_page
    
    page = max(1, page)  # Ensure page is at least 1
    per_page = max(1, min(500, per_page))  # Clamp per_page between 1 and 500
    offset = (page - 1) * per_page
    
    return page, per_page, offset


def calculate_pagination(total_items, page, per_page):
    """
    Calculate pagination metadata.
    
    Args:
        total_items: Total number of items
        page: Current page number
        per_page: Items per page
    
    Returns:
        dict: Pagination metadata
    """
    total_pages = (total_items + per_page - 1) // per_page if per_page > 0 else 1
    has_prev = page > 1
    has_next = page < total_pages
    
    return {
        'total_items': total_items,
        'total_pages': total_pages,
        'page': page,
        'per_page': per_page,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_page': page - 1 if has_prev else None,
        'next_page': page + 1 if has_next else None,
    }


def safe_int(value, default=0):
    """
    Safely convert a value to integer.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        int: Converted value or default
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def truncate_string(text, max_length=100, suffix='...'):
    """
    Truncate a string to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
    
    Returns:
        str: Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def flash_message(request, message, level='info'):
    """
    Add a flash message with the specified level.
    
    Args:
        request: HTTP request object
        message: Message text
        level: Message level (info, success, warning, error)
    """
    level_map = {
        'info': messages.INFO,
        'success': messages.SUCCESS,
        'warning': messages.WARNING,
        'error': messages.ERROR,
    }
    messages.add_message(request, level_map.get(level, messages.INFO), message)


def require_post(view_func):
    """
    Decorator that requires POST method.
    Returns 405 Method Not Allowed for other methods.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            if is_ajax_request(request):
                return json_error('Method not allowed', status=405)
            return redirect('database_list')
        return view_func(request, *args, **kwargs)
    return wrapper


def format_file_size(size_bytes):
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        str: Formatted size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def clean_input(value, strip=True, lower=False):
    """
    Clean and normalize input string.
    
    Args:
        value: Input value
        strip: Whether to strip whitespace
        lower: Whether to convert to lowercase
    
    Returns:
        str: Cleaned string or empty string if None
    """
    if value is None:
        return ''
    result = str(value)
    if strip:
        result = result.strip()
    if lower:
        result = result.lower()
    return result
