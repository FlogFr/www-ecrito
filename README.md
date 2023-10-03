# www-ecrito

Backend and Frontend of https://ecrito.fr/

PostgreSQL backed up
S3 backed up for files

Django CMS WagTail for all URLs
Django API on /api/

Copy production.py from configmap but do not include it in Git.

## Collect Static to S3

DJANGO_SETTINGS_MODULE='ecrito.settings.production' python manage.py collectstatic --no-input --clear

## Build Docker

docker build -t rg.fr-par.scw.cloud/ecrito/backend:latest .
docker push rg.fr-par.scw.cloud/ecrito/backend:latest
