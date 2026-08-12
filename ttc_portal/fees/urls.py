from django.urls import path
from fees import views

urlpatterns = [
    # GePG webhook — malipo yanathibitishwa kiotomatiki (csrf_exempt)
    path('api/gepg/notification/', views.gepg_notification, name='gepg_notification'),
    # Student actions (SR2-style)
    path('dashboard/generate/<int:bill_id>/', views.generate_control, name='generate_control'),
    path('dashboard/pay/<int:bill_id>/', views.submit_payment, name='submit_payment'),
    # College admin: fees & payments
    path('college-admin/ada/', views.admin_fees, name='admin_fees'),
    path('college-admin/ada/ongeza/', views.admin_fee_add, name='admin_fee_add'),
    path('college-admin/ada/<int:fee_id>/badilisha/', views.admin_fee_toggle, name='admin_fee_toggle'),
    path('college-admin/malipo/', views.admin_payments, name='admin_payments'),
    path('college-admin/malipo/<int:payment_id>/<str:action>/', views.admin_payment_confirm, name='admin_payment_confirm'),
]
