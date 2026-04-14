from django.contrib.auth.models import User
from management.models import Coach, Athlete

def check_user(username, password):
    u = User.objects.filter(username=username).first()
    if not u:
        print(f"User '{username}' not found.")
        return
    
    print(f"User found: {u.username}")
    print(f"Is Superuser: {u.is_superuser}")
    print(f"Is Coach: {Coach.objects.filter(user=u).exists()}")
    print(f"Is Athlete: {Athlete.objects.filter(user=u).exists()}")
    
    is_correct = u.check_password(password)
    print(f"Password '{password}' correct: {is_correct}")
    
    if not is_correct:
        # Check if password might be stored as plain text in the database (unlikely but possible if manually edited)
        # However, check_password handles the hashing. Let's see if we can find any user with this password.
        pass

print("--- Checking Coach Account ---")
check_user('Acer@123123', 'P@ssword')

print("\n--- Listing All Coaches ---")
for c in Coach.objects.all():
    print(f"Coach: {c.user.username}, Sports: {c.sports}")
