from django.contrib.auth.models import User
from management.models import Coach, Athlete

def sync_passwords():
    print("--- Syncing Coach Passwords ---")
    for coach in Coach.objects.all():
        if coach.plain_password:
            user = coach.user
            print(f"Syncing coach: {user.username} with password: {coach.plain_password}")
            user.set_password(coach.plain_password)
            user.save()
    
    print("\n--- Syncing Athlete Passwords ---")
    for athlete in Athlete.objects.all():
        if athlete.plain_password:
            user = athlete.user
            print(f"Syncing athlete: {user.username} with password: {athlete.plain_password}")
            user.set_password(athlete.plain_password)
            user.save()
    
    print("\nSync complete.")

sync_passwords()
