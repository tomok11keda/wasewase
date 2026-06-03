#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
# Django 標準の collectstatic（WhiteNoise）。cloudinary_storage は INSTALLED_APPS に入れない。
python manage.py collectstatic --noinput
python manage.py migrate --noinput
