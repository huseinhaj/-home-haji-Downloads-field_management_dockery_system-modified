import json

# Read the backup file
with open('backup.json', 'r') as f:
    data = json.load(f)

# Fix the data
fixed_data = []
for item in data:
    # Change auth.user to field_app.customuser
    if item.get('model') == 'auth.user':
        item['model'] = 'field_app.customuser'
        
        # Remove username field and ensure email is used
        if 'username' in item['fields']:
            # If email is empty, use username as email
            if not item['fields'].get('email'):
                item['fields']['email'] = item['fields']['username']
            del item['fields']['username']
    
    # Fix content_type references for customuser (4 -> 15)
    if item.get('model') == 'auth.permission':
        if item['fields'].get('content_type') == 4:  # auth.user
            item['fields']['content_type'] = 15  # field_app.customuser
    
    # Fix admin logentry user references
    if item.get('model') == 'admin.logentry':
        # We'll set these to null for now to avoid foreign key issues
        item['fields']['user'] = None
    
    fixed_data.append(item)

# Save the fixed backup
with open('backup_fixed.json', 'w') as f:
    json.dump(fixed_data, f, indent=2)

print("✅ Fixed backup saved as backup_fixed.json")
