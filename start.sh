#!/usr/bin/env bash
set -o errexit

# 永続ディスク上の本番DBに対してマイグレーションを適用してから起動する。
# Render の build フェーズではディスクがマウントされないため、ここで実行する。
python manage.py migrate --noinput
python manage.py ensure_superuser

exec gunicorn wasewase.wsgi --bind "0.0.0.0:${PORT}"
