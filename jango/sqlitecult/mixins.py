"""
Permission mixins for SQLite Cult views.
These mixins handle authorization for database operations.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse

from .models import DatabasePermissionChecker, SqliteFile


class DatabasePermissionMixin(LoginRequiredMixin):
    """
    Mixin that checks if user has permission to access a database.
    
    Attributes:
        require_write_permission: Set to True for views that modify data
        require_admin_permission: Set to True for views that delete databases or manage permissions
    """
    require_write_permission = False
    require_admin_permission = False
    
    def get_database_name(self):
        """Get the database name from the URL kwargs."""
        return self.kwargs.get('db_name')
    
    def check_permission(self, request):
        """Check if the user has the required permission."""
        db_name = self.get_database_name()
        if not db_name:
            return True, "No database specified"
        
        can_access, reason = DatabasePermissionChecker.can_access_database(
            request.user, 
            db_name,
            require_write=self.require_write_permission,
            require_admin=self.require_admin_permission
        )
        return can_access, reason
    
    def dispatch(self, request, *args, **kwargs):
        # First, let LoginRequiredMixin do its job
        response = super().dispatch(request, *args, **kwargs)
        
        # Check database permission
        can_access, reason = self.check_permission(request)
        
        if not can_access:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'error': f'Permission denied: {reason}'
                }, status=403)
            messages.error(request, f'Permission denied: {reason}')
            return redirect('database_list')
        
        return response


class DatabaseReadPermissionMixin(DatabasePermissionMixin):
    """Mixin for views that only need read access to a database."""
    require_write_permission = False
    require_admin_permission = False


class DatabaseWritePermissionMixin(DatabasePermissionMixin):
    """Mixin for views that need write access (modify tables, insert/update/delete rows)."""
    require_write_permission = True
    require_admin_permission = False


class DatabaseAdminPermissionMixin(DatabasePermissionMixin):
    """Mixin for views that need admin access (delete database, manage permissions)."""
    require_write_permission = True
    require_admin_permission = True


class DatabaseOwnerOrAdminMixin(LoginRequiredMixin):
    """
    Mixin that checks if user is the database owner or a superuser/staff.
    Used for operations like deleting a database or transferring ownership.
    """
    
    def get_database_name(self):
        """Get the database name from the URL kwargs."""
        return self.kwargs.get('db_name')
    
    def is_owner_or_admin(self, request):
        """Check if user is owner or admin."""
        db_name = self.get_database_name()
        if not db_name:
            return True
        
        if request.user.is_superuser or request.user.is_staff:
            return True
        
        sqlite_file = SqliteFile.get_by_actual_filename(db_name)
        if sqlite_file:
            return sqlite_file.owner == request.user
        return False
    
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        
        if not self.is_owner_or_admin(request):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'error': 'Only the database owner or administrator can perform this action.'
                }, status=403)
            messages.error(request, 'Only the database owner or administrator can perform this action.')
            return redirect('database_list')
        
        return response
