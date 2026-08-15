from django.urls import path
from fees import views

urlpatterns = [
    # GePG webhook — malipo yanathibitishwa kiotomatiki (csrf_exempt)
    path('api/gepg/notification/', views.gepg_notification, name='gepg_notification'),
    # Student actions (SR2-style)
    path('dashboard/generate/<int:bill_id>/', views.generate_control, name='generate_control'),
    path('dashboard/fetch-control-numbers/', views.student_fetch_control_numbers, name='student_fetch_control_numbers'),
    path('dashboard/pay/<int:bill_id>/', views.submit_payment, name='submit_payment'),
    # Mhasibu wa chuo: control numbers (mwanafunzi hawezi kuzalisha tena)
    path('college-admin/control-numbers/', views.admin_control_numbers, name='admin_control_numbers'),
    path('college-admin/control-numbers/generate/<int:bill_id>/', views.admin_control_generate, name='admin_control_generate'),
    path('college-admin/control-numbers/generate-all/', views.admin_control_generate_all, name='admin_control_generate_all'),
    # College admin: fees & payments
    path('college-admin/ada/', views.admin_fees, name='admin_fees'),
    path('college-admin/ada/ongeza/', views.admin_fee_add, name='admin_fee_add'),
    path('college-admin/ada/<int:fee_id>/badilisha/', views.admin_fee_toggle, name='admin_fee_toggle'),
    path('college-admin/malipo/', views.admin_payments, name='admin_payments'),
    path('college-admin/malipo/<int:payment_id>/<str:action>/', views.admin_payment_confirm, name='admin_payment_confirm'),
]
