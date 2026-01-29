# planners/urls.py.py
from django.urls import path
from . import views
from .views import *

app_name = 'planners'

urlpatterns = [
    path('', views.PlannerDashboardView.as_view(), name='planner_dashboard'),

    # Subdepartments
    path('subdepartments/', views.SubdepartmentListView.as_view(), name='subdepartment_list'),
    path('subdepartments/add/', views.SubdepartmentCreateView.as_view(), name='subdepartment_add'),
    path('subdepartments/<int:pk>/edit/', views.SubdepartmentUpdateView.as_view(), name='subdepartment_edit'),
    path('subdepartments/<int:pk>/delete/', views.SubdepartmentDeleteView.as_view(), name='subdepartment_delete'),

    # Operators
    path('operators/', views.OperatorListView.as_view(), name='operator_list'),
    path('operators/add/', views.OperatorCreateView.as_view(), name='operator_add'),
    path('operators/<int:pk>/edit/', views.OperatorUpdateView.as_view(), name='operator_edit'),
    path('operators/<int:pk>/delete/', views.OperatorDeleteView.as_view(), name='operator_delete'),
    path('operators/sync/', views.OperatorSyncView.as_view(), name='operator_sync'),

    # Users
    path('users/', views.TeamUserListView.as_view(), name='user_list'),
    path('users/<int:pk>/edit/', views.TeamUserUpdateView.as_view(), name='user_edit'),
    path('users/add/', views.TeamUserCreateView.as_view(), name='user_add'),

    # Calendar
    path('calendar/', views.CalendarListView.as_view(), name='calendar_list'),
    path('calendar/add/', views.CalendarBulkCreateView.as_view(), name='calendar_add'),
    path('calendar/delete/', views.CalendarBulkDeleteView.as_view(), name='calendar_delete'),

    # PRO
    path('pro/', views.ProListView.as_view(), name='pro_list'),
    path('pro/add/', views.ProCreateView.as_view(), name='pro_add'),
    path('pro/<int:pk>/edit/', views.ProUpdateView.as_view(), name='pro_edit'),
    path('pro/<int:pk>/delete/', views.ProDeleteView.as_view(), name='pro_delete'),
    path("pro/add-from-posummary/", POSummaryLookupView.as_view(), name="posummary_lookup"),
    path("pro/add-from-posummary/create/", POSummaryProCreateView.as_view(), name="posummary_pro_create"),
    path("pro/update-from-posummary/", UpdateAllProFromPOSummaryView.as_view(), name="pro_update_from_posummary",),

    # ROUTINGS
    path('routings/', views.RoutingListView.as_view(), name='routing_list'),
    path("routings/<int:routing_id>/operations/",RoutingOperationByRoutingListView.as_view(),name="routing_operation_by_routing"),
    path('routings/add/', views.RoutingCreateView.as_view(), name='routing_add'),
    path('routings/<int:pk>/edit/', views.RoutingUpdateView.as_view(), name='routing_edit'),
    path('routings/<int:pk>/delete/', views.RoutingDeleteView.as_view(), name='routing_delete'),
    path('routings/copy/', views.RoutingCopyStep1View.as_view(), name='routing_copy_step1'),
    path('routing/copy/quick/', views.RoutingCopyStep11View.as_view(), name='routing_copy_step11'),
    path('routings/copy/confirm/', views.RoutingCopyStep2View.as_view(), name='routing_copy_step2'),

    # OPERATIONS
    path('operations/', views.OperationListView.as_view(), name='operation_list'),
    path('operations/add/', views.OperationCreateView.as_view(), name='operation_add'),
    path('operations/<int:pk>/edit/', views.OperationUpdateView.as_view(), name='operation_edit'),
    path('operations/<int:pk>/delete/', views.OperationDeleteView.as_view(), name='operation_delete'),

    # ROUTING OPERATIONS
    path('routing-operations/', views.RoutingOperationListView.as_view(), name='routing_operation_list'),
    path('routing-operations/add/', views.RoutingOperationCreateView.as_view(), name='routing_operation_add'),
    path('routing-operations/<int:pk>/edit/', views.RoutingOperationUpdateView.as_view(),name='routing_operation_edit'),
    path('routing-operations/<int:pk>/delete/', views.RoutingOperationDeleteView.as_view(),name='routing_operation_delete'),

    # LOGIN OPERATORS (operator logins)
    path('login-operators/', views.LoginOperatorListView.as_view(), name='login_operator_list'),
    path('login-operators/add/', views.LoginOperatorCreateView.as_view(), name='login_operator_add'),
    path('login-operators/<int:pk>/edit/', views.LoginOperatorUpdateView.as_view(), name='login_operator_edit'),
    path('login-operators/<int:pk>/delete/', views.LoginOperatorDeleteView.as_view(), name='login_operator_delete'),
    path("login-operators/logout/wizard/", views.LoginOperatorLogoutWizardView.as_view(), name="login_operator_logout_wizard",),
    path("login-operators/logout/save/", views.LoginOperatorLogoutSaveView.as_view(), name="login_operator_logout_save",),
    path("login-operators/logout/cancel/", views.LoginOperatorLogoutCancelView.as_view(), name="login_operator_logout_cancel", ),

    # MANUAL AUTO-LOGOUT
    path('login-operators/manual-logout/',ManualLogoutOperatorsView.as_view(),name='manual_logout_operators'),

    # MANUAL AUTO BREAK 30
    path("login-operators/auto-break-30/",ManualAssignBreak30View.as_view(),name="manual_assign_break_30",),

    # DECLARATIONS
    path("declarations/", views.DeclarationListView.as_view(), name="declaration_list"),
    path('declarations/add/', DeclarationCreateView.as_view(), name='declaration_add'),
    path('declarations/wizard/', DeclarationWizardPlannerView.as_view(), name='declaration_wizard'),
    path('declarations/wizard/save/', DeclarationSavePlannerView.as_view(), name='declaration_save_planner'),
    path("declarations/wizard/cancel/", DeclarationWizardCancelView.as_view(), name="declaration_wizard_cancel"),
    path('declarations/<int:pk>/', DeclarationDetailView.as_view(), name='declaration_view'),
    path("declarations/<int:pk>/edit/", views.DeclarationUpdateView.as_view(), name="declaration_edit"),
    path("declarations/<int:pk>/delete/", views.DeclarationDeleteView.as_view(), name="declaration_delete"),

    # BREAKS
    path("breaks/", views.BreakListView.as_view(), name="break_list"),
    path("breaks/add/", views.BreakCreateView.as_view(), name="break_add"),
    path("breaks/<int:pk>/edit/", views.BreakUpdateView.as_view(), name="break_edit"),
    path("breaks/<int:pk>/delete/", views.BreakDeleteView.as_view(), name="break_delete"),

    # OPERATORBREAKS
    path("operator-breaks/", views.OperatorBreakListView.as_view(), name="operator_break_list"),
    path("operator-breaks/<int:pk>/edit/", views.OperatorBreakUpdateView.as_view(), name="operator_break_edit"),
    path("operator-breaks/declare/", views.OperatorBreakWizardView.as_view(), name="operator_break_declare"),
    path("operator-breaks/<int:pk>/delete/", views.OperatorBreakDeleteView.as_view(), name="operator_break_delete",),

    # OPERATOR CAPACITY
    path("operator-capacity/",OperatorCapacityTodayView.as_view(),name="operator_capacity_today",),

    # DOWNTIME
    path("downtimes/", DowntimeListView.as_view(), name="downtime_list"),
    path("downtimes/add/", DowntimeCreateView.as_view(), name="downtime_add"),
    path("downtimes/<int:pk>/edit/", DowntimeUpdateView.as_view(), name="downtime_edit"),

    # DOWNTIME DECLARATIONS
    path("downtime-declarations/",DowntimeDeclarationListView.as_view(),name="downtime_declaration_list",),
    path("downtime-declarations/wizard/",DowntimeDeclarationWizardView.as_view(),name="downtime_declaration_wizard",),
    path("downtime-declarations/wizard/save/",DowntimeDeclarationSaveView.as_view(),name="downtime_declaration_save",),
    path("downtime-declarations/wizard/cancel/",DowntimeDeclarationWizardCancelView.as_view(),name="downtime_declaration_wizard_cancel",),

    # AJAX endpoints
    path('ajax/routings/', ajax_get_routings, name='ajax_get_routings'),
    path('ajax/routing_operations/', ajax_get_routing_operations, name='ajax_get_routing_operations'),
    path('ajax/get_teamuser/', views.ajax_get_teamuser, name='ajax_get_teamuser'),
    path('ajax/team-user-active-logins/',views.ajax_team_user_active_logins,name='ajax_team_user_active_logins'),


]
