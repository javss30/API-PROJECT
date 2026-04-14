"""
URL configuration for athlete_records project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from management import views as management_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('', management_views.home, name='home'),
    path('about/', management_views.about_page, name='about_page'),
    path('players/', management_views.players_page, name='players_page'),
    path('matches/', management_views.matches_page, name='matches_page'),
    path('login/', management_views.unified_login, name='unified_login'),
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/signup/', management_views.signup, name='signup'),
    path('athletes/', include('management.urls')),
    path('portal/', include('management.portal_urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

