# core\urls.py.py

from django.contrib import admin
from django.urls import path, include
from core import views

app_name = 'core'

urlpatterns = [
    path('', views.main_page, name='main_page'),

    path('admin_dashboard', views.admin_dashboard, name='admin_dashboard'),
    path('login', views.login_view, name='login'),
    path('logout', views.logout_view, name='logout'),



]
