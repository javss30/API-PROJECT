import os
import django
from django.utils import timezone
from datetime import timedelta
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'athlete_records.settings')
django.setup()

from django.contrib.auth.models import User
from management.models import Athlete, BasketballStat, Attendance, TrainingSession, PerformanceRecord

def seed():
    players = [
        {"username": "mthompson", "first": "Marcus", "last": "Thompson", "pos": "Point Guard", "jersey": "3", "grade": "Senior", "contact": "555-0101"},
        {"username": "jmacasero", "first": "Johna", "last": "Macasero", "pos": "Shooting Guard", "jersey": "8", "grade": "Junior", "contact": "555-0102"},
        {"username": "sjenkins", "first": "Sarah", "last": "Jenkins", "pos": "Small Forward", "jersey": "15", "grade": "Sophomore", "contact": "555-0103"},
        {"username": "kdurant", "first": "Kevin", "last": "Durant", "pos": "Power Forward", "jersey": "35", "grade": "Senior", "contact": "555-0104"},
        {"username": "erodriguez", "first": "Elena", "last": "Rodriguez", "pos": "Center", "jersey": "21", "grade": "Freshman", "contact": "555-0105"},
    ]

    for p in players:
        user, created = User.objects.get_or_create(username=p['username'])
        if created:
            user.first_name = p['first']
            user.last_name = p['last']
            user.set_password('password123')
            user.save()

        athlete, _ = Athlete.objects.get_or_create(user=user)
        athlete.sports = "Basketball"
        athlete.jersey_number = p['jersey']
        athlete.position = p['pos']
        athlete.grade_level = p['grade']
        athlete.contact_number = p['contact']
        athlete.save()

        # Add basketball stat
        BasketballStat.objects.get_or_create(
            athlete=athlete, 
            defaults={
                'points': random.randint(10, 25), 
                'assists': random.randint(2, 10), 
                'rebounds': random.randint(5, 12),
                'speed': random.randint(10, 20)
            }
        )
        
        # Add 10 training sessions to represent history
        missed = random.randint(0, 3)
        if p['username'] == 'kdurant':
            missed = 11 # As per the intervention needed card in the photo

        total = 15
        
        att_qs = Attendance.objects.filter(athlete=athlete)
        if att_qs.count() < total:
            for i in range(total):
                is_missed = i < missed
                session, _ = TrainingSession.objects.get_or_create(
                    athlete=athlete,
                    session_date=timezone.now() - timedelta(days=i),
                    defaults={'status': 'Missed' if is_missed else 'Completed', 'sports': 'Basketball', 'duration_minutes': 60}
                )
                
                Attendance.objects.get_or_create(
                    athlete=athlete,
                    session=session,
                    defaults={'status': 'Absent' if is_missed else 'Present'}
                )
                
    print("Successfully seeded athletes and stats!")

if __name__ == '__main__':
    seed()
