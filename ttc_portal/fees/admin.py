from django.contrib import admin
from .models import FeeItem, FeeBill, Payment


@admin.register(FeeItem)
class FeeItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'college', 'category', 'amount', 'academic_year', 'year_of_study', 'is_active')
    list_filter = ('college', 'category', 'is_active')
    search_fields = ('name', 'college__name')


@admin.register(FeeBill)
class FeeBillAdmin(admin.ModelAdmin):
    list_display = ('student', 'fee_item', 'academic_year', 'amount', 'status', 'control_number')
    list_filter = ('status', 'academic_year', 'fee_item__college')
    search_fields = ('student__full_name', 'student__registration_number', 'control_number')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('student', 'bill', 'amount', 'method', 'reference', 'status', 'confirmed_at')
    list_filter = ('status', 'method')
    search_fields = ('student__full_name', 'reference', 'student__registration_number')
    date_hierarchy = 'created_at'
