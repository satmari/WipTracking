# core/views.py
from django.contrib.auth import logout, authenticate, login
from django.contrib import messages
from django.shortcuts import redirect, render

app_name = 'core'


def main_page(request):
    user = request.user

    if not user.is_authenticated:
        return render(request, 'core/main_page.html')

    if user.groups.filter(name__iexact='ADMINS').exists():
        # return redirect('core:admin_dashboard')
        return redirect('planners:planner_dashboard')

    elif user.groups.filter(name__iexact='PLANNERS').exists():
        return redirect('planners:planner_dashboard')

    elif user.groups.filter(name__iexact='TEAMS').exists():
        return redirect('teams:team_dashboard')

    return render(request, 'core/main_page.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            if user.groups.filter(name__iexact='PLANNERS').exists():
                return redirect('planners:planner_dashboard')
            elif user.groups.filter(name__iexact='ADMINS').exists():
                return redirect('core:admin_dashboard')
            elif user.groups.filter(name__iexact='TEAMS').exists():
                return redirect('teams:team_dashboard')
            else:
                return redirect('core:main_page')

        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'core/login.html')


def logout_view(request):
    logout(request)
    return redirect('core:login')


def admin_dashboard(request):
    return render(request, 'core/admin_dashboard.html')
