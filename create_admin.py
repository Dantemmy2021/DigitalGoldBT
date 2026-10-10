import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'okc_portal.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = "admin"
email = "admin@gmail.com"
password = "admin123"

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, email, password)
    print(f"Superuser {username} created!")
else:
    user = User.objects.get(username=username)
    user.set_password(password)
    user.save()
    print(f"Password for {username} reset to {password}!")