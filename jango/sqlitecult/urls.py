from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    # Authentication
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    
    # Database operations
    path('', views.DatabaseListView.as_view(), name='database_list'),
    path('create-database/', views.CreateDatabaseView.as_view(), name='create_database'),
    path('database/<str:db_name>/', views.DatabaseDetailView.as_view(), name='database_detail'),
    path('database/<str:db_name>/delete/', views.DeleteDatabaseView.as_view(), name='delete_database'),
    path('database/<str:db_name>/execute/', views.ExecuteQueryView.as_view(), name='execute_query'),
    path('database/<str:db_name>/history/', views.QueryHistoryView.as_view(), name='query_history'),
    
    # Permission management
    path('database/<str:db_name>/permissions/', views.DatabasePermissionsView.as_view(), name='database_permissions'),
    path('database/<str:db_name>/permissions/grant/', views.GrantPermissionView.as_view(), name='grant_permission'),
    path('database/<str:db_name>/permissions/update/<int:user_id>/', views.UpdatePermissionView.as_view(), name='update_permission'),
    path('database/<str:db_name>/permissions/revoke/<int:user_id>/', views.RevokePermissionView.as_view(), name='revoke_permission'),
    path('database/<str:db_name>/permissions/transfer/', views.TransferOwnershipView.as_view(), name='transfer_ownership'),
    
    # API Management
    path('database/<str:db_name>/toggle-api/', views.ToggleAPIView.as_view(), name='toggle_api'),
    path('database/<str:db_name>/regenerate-api-key/', views.RegenerateAPIKeyView.as_view(), name='regenerate_api_key'),
    path('database/<str:db_name>/claim-ownership/', views.ClaimOwnershipView.as_view(), name='claim_ownership'),
    
    # Table operations
    path('database/<str:db_name>/create-table/', views.CreateTableView.as_view(), name='create_table'),
    path('database/<str:db_name>/table/<str:table_name>/', views.TableDetailView.as_view(), name='table_detail'),
    path('database/<str:db_name>/table/<str:table_name>/drop/', views.DropTableView.as_view(), name='drop_table'),
    path('database/<str:db_name>/table/<str:table_name>/schema/', views.TableSchemaView.as_view(), name='table_schema'),
    path('database/<str:db_name>/table/<str:table_name>/update-metadata/', views.UpdateTableMetadataView.as_view(), name='update_table_metadata'),
    
    # Column operations
    path('database/<str:db_name>/table/<str:table_name>/add-column/', views.AddColumnView.as_view(), name='add_column'),
    path('database/<str:db_name>/table/<str:table_name>/bulk-add-columns/', views.BulkAddColumnsView.as_view(), name='bulk_add_columns'),
    path('database/<str:db_name>/table/<str:table_name>/bulk-drop-columns/', views.BulkDropColumnsView.as_view(), name='bulk_drop_columns'),
    path('database/<str:db_name>/table/<str:table_name>/drop-column/', views.DropColumnView.as_view(), name='drop_column'),
    path('database/<str:db_name>/table/<str:table_name>/modify-column/', views.ModifyColumnView.as_view(), name='modify_column'),
    
    # Index operations
    path('database/<str:db_name>/table/<str:table_name>/create-index/', views.CreateIndexView.as_view(), name='create_index'),
    path('database/<str:db_name>/table/<str:table_name>/drop-index/<str:index_name>/', views.DropIndexView.as_view(), name='drop_index'),
    
    # Row operations
    path('database/<str:db_name>/table/<str:table_name>/insert/', views.InsertRowView.as_view(), name='insert_row'),
    path('database/<str:db_name>/table/<str:table_name>/update/<int:rowid>/', views.UpdateRowView.as_view(), name='update_row'),
    path('database/<str:db_name>/table/<str:table_name>/delete/<int:rowid>/', views.DeleteRowView.as_view(), name='delete_row'),
    
    # Export/Import
    path('database/<str:db_name>/table/<str:table_name>/export/', views.ExportTableView.as_view(), name='export_table'),
    path('database/<str:db_name>/table/<str:table_name>/import/', views.ImportDataView.as_view(), name='import_data'),
    path('database/<str:db_name>/table/<str:table_name>/import-preview/', views.ImportPreviewView.as_view(), name='import_preview'),
    path('database/<str:db_name>/table/<str:table_name>/import-with-columns/', views.ImportWithColumnsView.as_view(), name='import_with_columns'),
    
    # Dashboard
    path('dashboards/', views.DashboardListView.as_view(), name='dashboard_list'),
    path('dashboards/create/', views.CreateDashboardView.as_view(), name='create_dashboard'),
    path('dashboards/<int:dashboard_id>/', views.DashboardView.as_view(), name='dashboard_detail'),
    path('dashboards/<int:dashboard_id>/edit/', views.EditDashboardView.as_view(), name='edit_dashboard'),
    path('dashboards/<int:dashboard_id>/delete/', views.DeleteDashboardView.as_view(), name='delete_dashboard'),
    path('dashboards/<int:dashboard_id>/set-default/', views.SetDefaultDashboardView.as_view(), name='set_default_dashboard'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('dashboard/create-chart/', views.CreateChartView.as_view(), name='create_chart'),
    path('dashboard/chart/<int:chart_id>/edit/', views.EditChartView.as_view(), name='edit_chart'),
    path('dashboard/chart/<int:chart_id>/delete/', views.DeleteChartView.as_view(), name='delete_chart'),
    path('dashboard/chart/<int:chart_id>/data/', views.ChartDataView.as_view(), name='chart_data'),
    path('dashboard/preview-chart/', views.PreviewChartView.as_view(), name='preview_chart'),
    path('api/database/<str:db_name>/schema/', views.DatabaseSchemaAPIView.as_view(), name='database_schema_api'),
    
    # REST API
    path('api/v1/database/<str:db_name>/tables/', api_views.APITableListView.as_view(), name='api_table_list'),
    path('api/v1/database/<str:db_name>/table/<str:table_name>/', api_views.APITableDataView.as_view(), name='api_table_data'),
    path('api/v1/database/<str:db_name>/table/<str:table_name>/<int:rowid>/', api_views.APIRowDetailView.as_view(), name='api_row_detail'),
]
