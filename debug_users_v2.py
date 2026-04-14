from django.contrib.auth.models import User
from management.models import Coach, Athlete

def check_user(username):
    u = User.objects.filter(username=username).first()
    if not u:
        print(f"User '{username}' not found.")
        return
    
    coach = Coach.objects.filter(user=u).first()
    athlete = Athlete.objects.filter(user=u).first()
    
    print(f"User: {u.username}")
    print(f"Plain Password (Model): {coach.plain_password if coach else (athlete.plain_password if athlete else 'N/A')}")
    
    # Try common passwords if the provided one failed
    passwords_to_try = ['P@ssword', 'Acer@123123', 'Password123']
    for p in passwords_to_try:
        if u.check_password(p):
            print(f"MATCH FOUND: Password is '{p}'")
            return
    
    print("No common password match found.")

print("--- Checking Acer@123123 ---")
check_user('Acer@123123')

print("\n--- Listing All Users with their Profile Password ---")
for c in Coach.objects.all():
    print(f"Coach: {c.user.username} | Plain: {c.plain_password}")
for a in Athlete.objects.all():
    print(f"Athlete: {a.user.username} | Plain: {a.plain_password}")
