from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from field_app import views  # Changed from ". import views" to import from your app
from curriculum import views as curriculum_views  # PWA manifest & service worker
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
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    
    
    # REST API
    path('api/v1/', include('field_app.api_urls')),

    # Your app's URLs
    path('', include('field_app.urls')),

    # School Results app
    path('shule/', include('results.urls')),

    # Teacher Transfer Matching app
    path('transfer/', include('transfer_app.urls', namespace='transfer')),

    # Muungano E-Learning Platform
    path('elearning/', include('elearning.urls')),

    # Muungano Curriculum — Scheme of Work, Lesson Plan & Logbook
    path('curriculum/', include('curriculum.urls')),

    # PWA: Progressive Web App — root-level manifest & service worker
    # (Must be at root for proper PWA scope / install behavior)
    path('manifest.json', curriculum_views.pwa_manifest, name='root_pwa_manifest'),
    path('sw.js', curriculum_views.pwa_service_worker, name='root_pwa_service_worker'),
]
