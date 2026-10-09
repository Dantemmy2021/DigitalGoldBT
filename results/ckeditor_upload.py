from ckeditor_uploader.views import upload, browse
from django.views.decorators.csrf import csrf_exempt

# This makes CKEditor upload work without CSRF errors
upload = csrf_exempt(upload)