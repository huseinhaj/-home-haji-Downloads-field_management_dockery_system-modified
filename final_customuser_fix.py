import json

# Read the syntax-fixed JSON
with open('backup_syntax_fixed.json', 'r') as f:
    data = json.load(f)

print(f"Processing {len(data)} items...")

# Fix for CustomUser migration
fixed_data = []
user_conversions = 0

for item in data:
    try:
        # Convert auth.user to field_app.customuser
        if item.get('model') == 'auth.user':
            item['model'] = 'field_app.customuser'
            user_conversions += 1
            
            fields = item['fields']
            # Handle username -> email conversion
            if 'username' in fields:
                if not fields.get('email') or not fields['email'].strip():
                    fields['email'] = fields['username']
                del fields['username']
        
        # Skip admin.logentry (they cause foreign key issues)
        elif item.get('model') == 'admin.logentry':
            continue
            
        # Update permissions content_type
        elif item.get('model') == 'auth.permission':
            if item['fields'].get('content_type') == 4:  # auth.user
                item['fields']['content_type'] = 15  # field_app.customuser
            fixed_data.append(item)
            
        else:
            fixed_data.append(item)
            
    except Exception as e:
        print(f"⚠️  Skipping item due to error: {e}")
        continue

print(f"✅ Converted {user_conversions} users to CustomUser")
print(f"✅ Final count: {len(fixed_data)} items")

# Save final version
with open('backup_ready_to_load.json', 'w') as f:
    json.dump(fixed_data, f, indent=2)

print("✅ Ready-to-load backup saved as backup_ready_to_load.json")
