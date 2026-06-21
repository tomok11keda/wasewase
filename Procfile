web: python manage.py migrate --noinput && python manage.py ensure_superuser && gunicorn wasewase.wsgi --bind 0.0.0.0:$PORT
