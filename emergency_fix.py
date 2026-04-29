# emergency_fix.py
import os

# Force ALLOWED_HOSTS for Render
os.environ['ALLOWED_HOSTS'] = 'field-management-1.onrender.com,.onrender.com,localhost,127.0.0.1,*'
os.environ['DEBUG'] = 'True'

# Write to settings.py
with open('field_management/settings.py', 'r') as f:
    content = f.read()

# Replace ALLOWED_HOSTS line
import re
new_content = re.sub(
    r"ALLOWED_HOSTS\s*=\s*\[.*?\]",
    "ALLOWED_HOSTS = ['field-management-1.onrender.com', '.onrender.com', 'localhost', '127.0.0.1', '*']",
    content,
    flags=re.DOTALL
)

with open('field_management/settings.py', 'w') as f:
    f.write(new_content)

print("✅ Emergency fix applied!")
