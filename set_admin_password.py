
from django.contrib.auth import get_user_model

User = get_user_model()

try:
    user = User.objects.get(username='admin')
    user.set_password('admin')
    user.save()
    print("Password for 'admin' set successfully")
except User.DoesNotExist:
    print("User 'admin' does not exist")
