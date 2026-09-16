"""
Data migration: bridges zilizoachwa na token tupu (kabla ya default
ya token kuongezwa) zinapata token mpya moja kwa moja.
"""
from django.db import migrations

from results.bridge_models import generate_bridge_token


def fill_empty_tokens(apps, schema_editor):
    SahishiBridge = apps.get_model('results', 'SahishiBridge')
    for bridge in SahishiBridge.objects.filter(token='') | SahishiBridge.objects.filter(token__isnull=True):
        bridge.token = generate_bridge_token()
        bridge.save(update_fields=['token'])


def reverse_func(apps, schema_editor):
    # Hakuna cha kurejesha — tokens zilizojazwa zinabaki
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('results', '0046_sahishibridge_scanjob'),
    ]

    operations = [
        migrations.RunPython(fill_empty_tokens, reverse_func),
    ]
