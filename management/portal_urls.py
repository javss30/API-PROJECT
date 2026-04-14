
from django.urls import path
from . import views

urlpatterns = [
    path('', views.athlete_portal_landing, name='athlete_portal_landing'),
    path('login/', views.athlete_login, name='athlete_portal_login'),
    path('register/', views.register_athlete, name='athlete_portal_registration'),
    path('dashboard/', views.athlete_dashboard, name='athlete_portal_dashboard'),
    path('profile/', views.athlete_profile_update, name='athlete_portal_profile'),
]
