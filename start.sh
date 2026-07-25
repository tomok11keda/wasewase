#!/usr/bin/env bash
set -o errexit

# 永続ディスク上の本番DBに対してマイグレーションを適用してから起動する。
# Render の build フェーズではディスクがマウントされないため、ここで実行する。
python manage.py collectstatic --noinput

if [ ! -f staticfiles/admin/css/base.css ]; then
  echo "ERROR: collectstatic incomplete — admin/css/base.css missing." >&2
  ls -la staticfiles 2>/dev/null || echo "(no staticfiles dir)" >&2
  ls -la static/js 2>/dev/null || echo "(no static/js dir)" >&2
  exit 1
fi

if [ ! -f staticfiles/js/ugc_report.js ]; then
  echo "ERROR: collectstatic incomplete — js/ugc_report.js missing." >&2
  ls -la static/js 2>/dev/null || true
  ls -la staticfiles/js 2>/dev/null || true
  exit 1
fi

python manage.py migrate --noinput
python manage.py ensure_superuser

exec gunicorn wasewase.wsgi --bind "0.0.0.0:${PORT}"
