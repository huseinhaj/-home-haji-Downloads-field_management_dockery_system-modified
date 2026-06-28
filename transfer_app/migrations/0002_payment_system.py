from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transfer_app', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditBalance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('session_key', models.CharField(max_length=64, unique=True)),
                ('credits', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Credit Balance',
                'verbose_name_plural': 'Credit Balances',
                'app_label': 'transfer_app',
            },
        ),
        migrations.CreateModel(
            name='UnlockedContact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('session_key', models.CharField(db_index=True, max_length=64)),
                ('unlocked_teacher_id', models.IntegerField()),
                ('unlocked_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Unlocked Contact',
                'app_label': 'transfer_app',
            },
        ),
        migrations.CreateModel(
            name='PaymentRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('session_key', models.CharField(max_length=64)),
                ('teacher_name', models.CharField(blank=True, max_length=200)),
                ('contact_phone', models.CharField(blank=True, max_length=20)),
                ('package', models.CharField(
                    choices=[
                        ('single', 'Namba 1 — TZS 1,000'),
                        ('pack5', 'Namba 5 — TZS 3,500'),
                        ('unlimited3', 'Unlimited (Miezi 3) — TZS 8,000'),
                    ],
                    max_length=20,
                )),
                ('mpesa_ref', models.CharField(max_length=100, verbose_name='Kumb. ya Malipo (Mpesa/Tigo/Airtel)')),
                ('amount', models.PositiveIntegerField()),
                ('status', models.CharField(
                    choices=[('pending', 'Inasubiri'), ('approved', 'Imeidhinishwa'), ('rejected', 'Imekataliwa')],
                    default='pending',
                    max_length=20,
                )),
                ('credits_awarded', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'Ombi la Malipo',
                'verbose_name_plural': 'Maombi ya Malipo',
                'ordering': ['-created_at'],
                'app_label': 'transfer_app',
            },
        ),
        migrations.AlterUniqueTogether(
            name='unlockedcontact',
            unique_together={('session_key', 'unlocked_teacher_id')},
        ),
    ]
