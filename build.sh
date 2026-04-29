#!/bin/bash
# build.sh

# ... code yako ...

# Apply database migrations
echo "🔄 Applying database migrations..."
python manage.py migrate --noinput

# 🔥 TEMPORARY FIX: Kwa ajili ya test tu
echo "🔧 Setting ALLOWED_HOSTS temporarily..."
python manage.py shell -c "
from django.conf import settings
settings.ALLOWED_HOSTS = ['*']
print('ALLOWED_HOSTS set to allow all hosts')
"

echo "✅ Build completed successfully!"
