# fix_render_settings.py
import os

def fix_settings():
    settings_path = 'field_management/settings.py'
    
    with open(settings_path, 'r') as f:
        content = f.read()
    
    # 1. Fix DEBUG
    if "DEBUG = True" in content:
        content = content.replace(
            "DEBUG = True",
            "DEBUG = os.environ.get('DEBUG', 'False') == 'True'"
        )
    
    # 2. Fix ALLOWED_HOSTS
    if "ALLOWED_HOSTS = []" in content:
        content = content.replace(
            "ALLOWED_HOSTS = []",
            "# Render deployment hosts\nALLOWED_HOSTS = ['field-management-1.onrender.com', 'localhost', '127.0.0.1', '0.0.0.0']"
        )
    
    # 3. Replace DATABASES section
    old_db_config = '''DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'field_db',
        'USER': 'hajiuser',
        'PASSWORD': 'hajipassword',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}'''
    
    new_db_config = '''# Database configuration for Render
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600
    )
}'''
    
    if old_db_config in content:
        content = content.replace(old_db_config, new_db_config)
    
    # 4. Add Whitenoise middleware
    middleware_line = "'django.middleware.security.SecurityMiddleware',"
    if middleware_line in content:
        content = content.replace(
            middleware_line,
            "'django.middleware.security.SecurityMiddleware',\n    'whitenoise.middleware.WhiteNoiseMiddleware',"
        )
    
    # 5. Add static files configuration
    static_section = "STATIC_URL = 'static/'"
    if static_section in content:
        new_static_config = '''# Static files configuration
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Whitenoise for static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type'''
        
        # Find and replace from STATIC_URL to DEFAULT_AUTO_FIELD
        lines = content.split('\n')
        new_lines = []
        skip_until_default = False
        
        for i, line in enumerate(lines):
            if "STATIC_URL = 'static/'" in line:
                new_lines.append(new_static_config)
                skip_until_default = True
            elif "DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'" in line and skip_until_default:
                new_lines.append(line)
                skip_until_default = False
            elif not skip_until_default:
                new_lines.append(line)
        
        content = '\n'.join(new_lines)
    
    # 6. Add os import if not present
    if "import os" not in content.split('\n')[0:5]:
        lines = content.split('\n')
        lines.insert(1, "import os")
        content = '\n'.join(lines)
    
    # Write back
    with open(settings_path, 'w') as f:
        f.write(content)
    
    print("✅ Settings fixed for Render deployment")

if __name__ == "__main__":
    fix_settings()
