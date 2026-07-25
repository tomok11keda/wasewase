#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
# 管理画面 CSS 等を staticfiles/ に集める（Render 本番で WhiteNoise が配信）
python manage.py collectstatic --noinput
if [ ! -f staticfiles/admin/css/base.css ]; then
  echo "ERROR: collectstatic failed — admin static files missing." >&2
  exit 1
fi
if [ ! -f staticfiles/js/ugc_report.js ]; then
  echo "ERROR: collectstatic failed — ugc_report.js missing." >&2
  ls -la static/js >&2 || true
  exit 1
fi
# 本番 SQLite は永続ディスク上のため、build 時の migrate / ensure_superuser は効かない。
# これらは start.sh（起動時）で実行する。
