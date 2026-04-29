# Read the file as text
with open('backup.json', 'r') as f:
    content = f.read()

print("Fixing JSON syntax...")

# Fix 1: Add comma between objects at the end if missing
if '"expire_date": "2025-08-09T14:38:46.857Z"}}' in content:
    content = content.replace('"expire_date": "2025-08-09T14:38:46.857Z"}}', '"expire_date": "2025-08-09T14:38:46.857Z"}},')

# Fix 2: Ensure proper JSON array format
if not content.strip().startswith('['):
    content = '[' + content
if not content.strip().endswith(']'):
    content = content + ']'

# Fix 3: Add commas between all objects
content = content.replace('}{', '},{')
content = content.replace('}]', '}]')  # Fix double brackets

# Fix 4: Remove trailing comma before closing bracket
content = content.replace(',]', ']')

# Write fixed file
with open('backup_syntax_fixed.json', 'w') as f:
    f.write(content)

print("✅ Fixed JSON syntax saved as backup_syntax_fixed.json")

# Verify
import json
try:
    with open('backup_syntax_fixed.json', 'r') as f:
        test_data = json.load(f)
    print(f"✅ JSON is valid! Contains {len(test_data)} items")
except json.JSONDecodeError as e:
    print(f"❌ Still has error: {e}")
