from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from field_app import views  # Changed from ". import views" to import from your app
from field_app.admin import custom_admin_site

urlpatterns = [
    
    path('admin/', custom_admin_site.urls),
    # Authentication URLs
    path('accounts/login/', 
        auth_views.LoginView.as_view(template_name='registration/login.html'), 
        name='login'),
    path('accounts/logout/', 
        auth_views.LogoutView.as_view(), 
        name='logout'),
    path('accounts/password_reset/',
        auth_views.PasswordResetView.as_view(template_name='registration/password_reset.html'),
        name='password_reset'),
    
    # Registration - now correctly pointing to your app's views
    path('accounts/register/', views.register, name='register'),
    
    # Your app's URLs
    path('', include('field_app.urls')),
]
