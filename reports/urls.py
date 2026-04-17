
from django.urls import path
from . import views


app_name = 'reports'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('upload/', views.upload_report, name='upload_report'),
    path('history/', views.history, name='history'),
    path('delete/<int:pk>/', views.delete_report, name='delete_report'),
    path('approve/<int:pk>/', views.approve_report, name='approve_report'),
    path('refuse/<int:pk>/', views.refuse_report, name='refuse_report'),
    path('users/', views.manage_users, name='manage_users'),
    path('profil/', views.profil, name='profil'),
]

