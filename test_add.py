import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'athlete_records.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from management.models import Athlete, Coach, Incident, Evaluation

coach_user = User.objects.filter(coach__isnull=False).first()
athlete = Athlete.objects.first()

client = Client()
client.force_login(coach_user)

# Test Add Evaluation
resp1 = client.post(f'/athletes/monitor-progress/add-evaluation/{athlete.id}/', {
    'notes': 'Test feedback text from script'
})

print("Eval form success:", Evaluation.objects.filter(notes='Test feedback text from script').exists())

# Test Incident
from datetime import date
resp2 = client.post('/athletes/log-incident/', {
    'athlete_id': athlete.id,
    'description': 'Test incident report from script',
    'date': str(date.today())
})

print("Incident success:", Incident.objects.filter(description='Test incident report from script').exists())

