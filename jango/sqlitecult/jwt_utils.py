"""
JWT utilities for API authentication.
Handles token generation, validation, and permission encoding.
"""
import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from typing import Optional

from .constants import (
    API_PERMISSION_READ, API_PERMISSION_CREATE,
    API_PERMISSION_UPDATE, API_PERMISSION_DELETE
)


class JWTManager:
    """
    Manager for JWT token operations.
    Handles token creation and validation with embedded permissions.
    """
    
    @staticmethod
    def generate_token(
        sqlite_file_id: int,
        database_name: str,
        permissions: list[str],
        expiration_days: int = None
    ) -> str:
        """
        Generate a JWT token for API access.
        
        Args:
            sqlite_file_id: The ID of the SqliteFile model instance
            database_name: The display name of the database
            permissions: List of permission strings (read, create, update, delete)
            expiration_days: Days until expiration (default from settings)
            
        Returns:
            str: The encoded JWT token
        """
        if expiration_days is None:
            expiration_days = getattr(settings, 'JWT_EXPIRATION_DAYS', 365)
        
        payload = {
            'sqlite_file_id': sqlite_file_id,
            'database_name': database_name,
            'permissions': permissions,
            'iat': datetime.now(timezone.utc),
            'exp': datetime.now(timezone.utc) + timedelta(days=expiration_days),
        }
        
        token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        
        return token
    
    @staticmethod
    def decode_token(token: str) -> tuple[Optional[dict], Optional[str]]:
        """
        Decode and validate a JWT token.
        
        Args:
            token: The JWT token string
            
        Returns:
            tuple: (payload dict, error message) - one will be None
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload, None
        except jwt.ExpiredSignatureError:
            return None, 'Token has expired'
        except jwt.InvalidTokenError as e:
            return None, f'Invalid token: {str(e)}'
    
    @staticmethod
    def has_permission(payload: dict, permission: str) -> bool:
        """
        Check if a token payload has a specific permission.
        
        Args:
            payload: Decoded JWT payload
            permission: Permission to check (read, create, update, delete)
            
        Returns:
            bool: True if permission is granted
        """
        permissions = payload.get('permissions', [])
        return permission in permissions
    
    @staticmethod
    def can_read(payload: dict) -> bool:
        """Check if token has read permission."""
        return JWTManager.has_permission(payload, API_PERMISSION_READ)
    
    @staticmethod
    def can_create(payload: dict) -> bool:
        """Check if token has create permission."""
        return JWTManager.has_permission(payload, API_PERMISSION_CREATE)
    
    @staticmethod
    def can_update(payload: dict) -> bool:
        """Check if token has update permission."""
        return JWTManager.has_permission(payload, API_PERMISSION_UPDATE)
    
    @staticmethod
    def can_delete(payload: dict) -> bool:
        """Check if token has delete permission."""
        return JWTManager.has_permission(payload, API_PERMISSION_DELETE)
    
    @staticmethod
    def get_all_permissions() -> list[str]:
        """Get a list of all available permissions."""
        return [
            API_PERMISSION_READ,
            API_PERMISSION_CREATE,
            API_PERMISSION_UPDATE,
            API_PERMISSION_DELETE
        ]


def extract_token_from_header(auth_header: str) -> Optional[str]:
    """
    Extract JWT token from Authorization header.
    
    Supports both 'Bearer <token>' and plain '<token>' formats.
    
    Args:
        auth_header: The Authorization header value
        
    Returns:
        str: The token, or None if not found
    """
    if not auth_header:
        return None
    
    parts = auth_header.split()
    
    if len(parts) == 1:
        # Plain token format
        return parts[0]
    elif len(parts) == 2 and parts[0].lower() == 'bearer':
        # Bearer token format
        return parts[1]
    
    return None
