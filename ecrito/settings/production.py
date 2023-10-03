from .base import *

DEBUG = False

try:
    from .local import *
except ImportError:
    pass

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "5jhZhtGg1VtVy04paoelgymGQJ5isxh4pgmimqxtPURAwGASKZ4fihLpuckuXEJN_1p5NGkBR3rGLTlUCmCnNkkhTMARpq-7g"

# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html
# django < 4.2
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

# AWS Settings
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html
AWS_S3_REGION_NAME = "fr-par"
AWS_S3_ACCESS_KEY_ID = "SCW6XZEJ811AQBET2NQ6"
AWS_S3_SECRET_ACCESS_KEY = "3f6245e7-1684-4126-b3a2-f7742d96a96b"
AWS_STORAGE_BUCKET_NAME = "ecrito"
AWS_DEFAULT_ACL = 'public-read'
AWS_S3_ENDPOINT_URL = 'https://ecrito.s3.fr-par.scw.cloud'

# s3 static settings
AWS_LOCATION = 'static'
STATIC_URL = f'https://ecrito.s3.fr-par.scw.cloud/{AWS_LOCATION}/'
# django < 4.2
STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = ["*"]
