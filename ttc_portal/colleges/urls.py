from django.urls import path
from colleges import views

urlpatterns = [
    path('', views.home, name='home'),
    path('colleges/<str:code>/', views.college_detail, name='college_detail'),
    path('api/programs/', views.programs_api, name='programs_api'),
]
