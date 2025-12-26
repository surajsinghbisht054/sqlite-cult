from django.contrib import admin
from .models import DatabaseAccess, QueryHistory, Dashboard, DashboardChart, DatabaseOwnership, DatabasePermission


@admin.register(DatabaseOwnership)
class DatabaseOwnershipAdmin(admin.ModelAdmin):
    list_display = ['database_name', 'owner', 'created_at']
    list_filter = ['created_at']
    search_fields = ['database_name', 'owner__username']
    ordering = ['-created_at']
    raw_id_fields = ['owner']


@admin.register(DatabasePermission)
class DatabasePermissionAdmin(admin.ModelAdmin):
    list_display = ['database_name', 'granted_to', 'permission_level', 'granted_by', 'created_at']
    list_filter = ['permission_level', 'created_at']
    search_fields = ['database_name', 'granted_to__username', 'granted_by__username']
    ordering = ['-created_at']
    raw_id_fields = ['granted_to', 'granted_by']


@admin.register(DatabaseAccess)
class DatabaseAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'database_name', 'last_accessed', 'created_at']
    list_filter = ['database_name', 'created_at']
    search_fields = ['user__username', 'database_name']
    ordering = ['-last_accessed']


@admin.register(QueryHistory)
class QueryHistoryAdmin(admin.ModelAdmin):
    list_display = ['user', 'database_name', 'query_preview', 'success', 'executed_at']
    list_filter = ['success', 'database_name', 'executed_at']
    search_fields = ['user__username', 'database_name', 'query']
    ordering = ['-executed_at']
    
    def query_preview(self, obj):
        return obj.query[:50] + '...' if len(obj.query) > 50 else obj.query
    query_preview.short_description = 'Query'


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_default', 'chart_count', 'created_at', 'updated_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['name', 'user__username', 'description']
    ordering = ['-created_at']
    
    def chart_count(self, obj):
        return obj.charts.count()
    chart_count.short_description = 'Charts'


@admin.register(DashboardChart)
class DashboardChartAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'dashboard', 'chart_type', 'database_name', 'created_at']
    list_filter = ['chart_type', 'database_name', 'dashboard', 'created_at']
    search_fields = ['title', 'user__username', 'query']
    ordering = ['-created_at']
