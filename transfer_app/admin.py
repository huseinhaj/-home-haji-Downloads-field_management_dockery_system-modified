from django.contrib import admin
from django.utils import timezone
from .models import TeacherTransfer, CreditBalance, UnlockedContact, PaymentRequest, CREDIT_PACKAGES


class TransferModelAdmin(admin.ModelAdmin):
    """Base admin that routes all queries to the 'transfer' database."""

    def get_queryset(self, request):
        return super().get_queryset(request).using('transfer')

    def save_model(self, request, obj, form, change):
        obj.save(using='transfer')

    def delete_model(self, request, obj):
        obj.delete(using='transfer')

    def delete_queryset(self, request, queryset):
        queryset.using('transfer').delete()


@admin.action(description='✅ Idhinisha malipo na ongeza credits')
def approve_payments(modeladmin, request, queryset):
    approved = 0
    for payment in queryset.using('transfer').filter(status='pending'):
        pkg = CREDIT_PACKAGES.get(payment.package)
        if not pkg:
            continue
        credits_to_add = pkg['credits']
        balance, _ = CreditBalance.objects.using('transfer').get_or_create(
            session_key=payment.session_key,
            defaults={'credits': 0}
        )
        balance.credits += credits_to_add
        balance.save(using='transfer')
        payment.status = 'approved'
        payment.credits_awarded = credits_to_add
        payment.reviewed_at = timezone.now()
        payment.save(using='transfer')
        approved += 1
    modeladmin.message_user(request, f'{approved} malipo yameidhinishwa. Credits zimeongezwa.')


@admin.action(description='❌ Kataa malipo')
def reject_payments(modeladmin, request, queryset):
    count = queryset.using('transfer').filter(status='pending').update(
        status='rejected',
        reviewed_at=timezone.now(),
    )
    modeladmin.message_user(request, f'{count} malipo yamekataliwa.')


@admin.register(TeacherTransfer)
class TeacherTransferAdmin(TransferModelAdmin):
    list_display  = ['name', 'current_school', 'district_name', 'region_name', 'level', 'is_active', 'created_at']
    list_filter   = ['level', 'is_active', 'location_type']
    search_fields = ['name', 'phone', 'current_school', 'district_name', 'region_name']
    readonly_fields = ['session_key', 'created_at', 'updated_at']
    list_per_page = 50


@admin.register(PaymentRequest)
class PaymentRequestAdmin(TransferModelAdmin):
    list_display  = ['teacher_name', 'contact_phone', 'package', 'amount', 'mpesa_ref', 'status', 'created_at']
    list_filter   = ['status', 'package']
    search_fields = ['teacher_name', 'contact_phone', 'mpesa_ref', 'session_key']
    readonly_fields = ['session_key', 'created_at', 'reviewed_at', 'credits_awarded']
    actions       = [approve_payments, reject_payments]
    list_per_page = 50

    def get_list_display_links(self, request, list_display):
        return ['teacher_name']


@admin.register(CreditBalance)
class CreditBalanceAdmin(TransferModelAdmin):
    list_display  = ['session_key', 'credits', 'updated_at']
    search_fields = ['session_key']
    list_per_page = 50


@admin.register(UnlockedContact)
class UnlockedContactAdmin(TransferModelAdmin):
    list_display  = ['session_key', 'unlocked_teacher_id', 'unlocked_at']
    search_fields = ['session_key']
    list_per_page = 50
