from django import forms


class CreateDatabaseForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Database name (e.g., mydb)',
            'pattern': '[a-zA-Z0-9_-]+',
            'title': 'Only letters, numbers, underscores, and hyphens allowed'
        })
    )
    
    def clean_name(self):
        name = self.cleaned_data['name']
        # Remove any path separators for security
        name = name.replace('/', '').replace('\\', '').replace('..', '')
        return name


class CreateTableForm(forms.Form):
    table_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Table name'
        })
    )
    columns = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input',
            'placeholder': 'id INTEGER PRIMARY KEY AUTOINCREMENT,\nname TEXT NOT NULL,\nemail TEXT UNIQUE,\ncreated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'rows': 4
        })
    )


class AddColumnForm(forms.Form):
    COLUMN_TYPES = [
        ('TEXT', 'TEXT'),
        ('INTEGER', 'INTEGER'),
        ('REAL', 'REAL'),
        ('BLOB', 'BLOB'),
        ('NUMERIC', 'NUMERIC'),
        ('BOOLEAN', 'BOOLEAN'),
        ('DATE', 'DATE'),
        ('DATETIME', 'DATETIME'),
        ('TIMESTAMP', 'TIMESTAMP'),
    ]
    
    column_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Column name'
        })
    )
    column_type = forms.ChoiceField(
        choices=COLUMN_TYPES,
        widget=forms.Select(attrs={
            'class': 'form-input'
        })
    )
    default_value = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Default value (optional)'
        })
    )


class CreateIndexForm(forms.Form):
    index_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Index name'
        })
    )
    columns = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Column names (comma separated)'
        })
    )
    unique = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-checkbox'
        })
    )


class ImportDataForm(forms.Form):
    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-input',
            'accept': '.json,.csv'
        })
    )


class InsertRowForm(forms.Form):
    """Dynamic form - will be generated based on table columns"""
    pass


class ExecuteQueryForm(forms.Form):
    query = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input query-input',
            'placeholder': 'Enter your SQL query here...\nExample: SELECT * FROM users WHERE id > 10',
            'rows': 4
        })
    )
