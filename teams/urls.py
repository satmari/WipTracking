# teams/urls.py.py
from django.urls import path
from . import views
from .views import *

app_name = 'teams'

urlpatterns = [
    path('dashboard/', TeamDashboardView.as_view(), name='team_dashboard'),
    path('operators/login/', OperatorLoginView.as_view(), name='operator_login'),
    path('operators/logout/', OperatorLogoutView.as_view(), name='operator_logout'),

    path('declare-output/', DeclarationWizardView.as_view(), name='declare_output'),
    path('declare-output/save/', DeclarationSaveView.as_view(), name='declare_output_save'),
    path('declare-output/cancel/', DeclarationWizardCancelView.as_view(), name='declare_output_cancel'),
]