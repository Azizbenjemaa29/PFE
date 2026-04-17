from django.urls import include, path
from django.contrib.auth import views as auth_views
from django.contrib import admin
from blog import views

urlpatterns = [

    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    path('reports/', include(('reports.urls', 'reports'), namespace='reports')),]