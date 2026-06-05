#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
# 管理画面 CSS 等を staticfiles/ に集める（Render 本番で WhiteNoise が配信）
python manage.py collectstatic --noinput
if [ ! -f staticfiles/admin/css/base.css ]; then
  echo "ERROR: collectstatic failed — admin static files missing." >&2
  exit 1
fi
python manage.py migrate --noinput
python manage.py ensure_superuser
