from django.conf import settings

def django_env(request):
    return {
        "DJANGO_ENV": settings.DJANGO_ENV
    }
