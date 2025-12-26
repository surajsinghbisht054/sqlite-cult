import json
from django.views import View
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .models import DatabaseOwnership, SQLiteManager

class APIAuthMixin:
    def dispatch(self, request, *args, **kwargs):
        self.db_name = kwargs.get('db_name')
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return JsonResponse({'error': 'Missing API Key'}, status=401)
            
        try:
            ownership = DatabaseOwnership.objects.get(database_name=self.db_name)
            if not ownership.api_enabled:
                return JsonResponse({'error': 'API access is disabled for this database'}, status=403)
            
            if ownership.api_secret_key != api_key:
                return JsonResponse({'error': 'Invalid API Key'}, status=401)
                
        except DatabaseOwnership.DoesNotExist:
            return JsonResponse({'error': 'Database not found'}, status=404)
            
        return super().dispatch(request, *args, **kwargs)

@method_decorator(csrf_exempt, name='dispatch')
class APITableListView(APIAuthMixin, View):
    def get(self, request, db_name):
        try:
            tables = SQLiteManager.get_tables(db_name)
            return JsonResponse({'tables': tables})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class APITableDataView(APIAuthMixin, View):
    def get(self, request, db_name, table_name):
        # Pagination
        try:
            limit = int(request.GET.get('limit', 50))
            offset = int(request.GET.get('offset', 0))
        except ValueError:
            return JsonResponse({'error': 'Invalid limit or offset'}, status=400)
            
        try:
            rows = SQLiteManager.get_rows(db_name, table_name, limit, offset)
            columns_info = SQLiteManager.get_table_info(db_name, table_name)
            columns = [col[1] for col in columns_info]
            
            data = []
            for row in rows:
                # row[0] is rowid, rest are columns
                row_dict = {'rowid': row[0]}
                for i, col in enumerate(columns):
                    row_dict[col] = row[i+1]
                data.append(row_dict)
                
            return JsonResponse({
                'columns': columns,
                'data': data,
                'count': len(data),
                'limit': limit,
                'offset': offset
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def post(self, request, db_name, table_name):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
            
        try:
            columns_info = SQLiteManager.get_table_info(db_name, table_name)
            valid_columns = [col[1] for col in columns_info]
            
            insert_columns = []
            insert_values = []
            
            for col, val in data.items():
                if col in valid_columns:
                    insert_columns.append(col)
                    insert_values.append(val)
            
            if not insert_columns:
                return JsonResponse({'error': 'No valid columns provided'}, status=400)
                
            SQLiteManager.insert_row(db_name, table_name, insert_columns, insert_values)
            return JsonResponse({'success': True, 'message': 'Row created'}, status=201)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class APIRowDetailView(APIAuthMixin, View):
    def get(self, request, db_name, table_name, rowid):
        try:
            row = SQLiteManager.get_row_by_rowid(db_name, table_name, rowid)
            if not row:
                return JsonResponse({'error': 'Row not found'}, status=404)
                
            columns_info = SQLiteManager.get_table_info(db_name, table_name)
            columns = [col[1] for col in columns_info]
            
            row_dict = {'rowid': row[0]}
            for i, col in enumerate(columns):
                row_dict[col] = row[i+1]
                
            return JsonResponse(row_dict)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def put(self, request, db_name, table_name, rowid):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
            
        try:
            columns_info = SQLiteManager.get_table_info(db_name, table_name)
            valid_columns = [col[1] for col in columns_info]
            
            update_columns = []
            update_values = []
            
            for col, val in data.items():
                if col in valid_columns:
                    update_columns.append(col)
                    update_values.append(val)
                    
            if not update_columns:
                return JsonResponse({'error': 'No valid columns provided'}, status=400)
                
            SQLiteManager.update_row(db_name, table_name, update_columns, update_values, rowid)
            return JsonResponse({'success': True, 'message': 'Row updated'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def delete(self, request, db_name, table_name, rowid):
        try:
            SQLiteManager.delete_row(db_name, table_name, rowid)
            return JsonResponse({'success': True, 'message': 'Row deleted'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
