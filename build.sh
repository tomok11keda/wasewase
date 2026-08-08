#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# React SPA 資産（WASE_REACT_SPA 有効時に /static/frontend/ から配信）
ensure_npm() {
  if command -v npm >/dev/null 2>&1; then
    return 0
  fi
  echo "npm not found; installing Node.js via nvm..." >&2
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  fi
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  nvm install 20
  nvm use 20
}

if [ -f frontend/package.json ]; then
  ensure_npm
  npm --prefix frontend ci
  npm --prefix frontend run build
  if [ ! -f static/frontend/assets/main.js ] && [ ! -f static/frontend/.vite/manifest.json ]; then
    echo "ERROR: frontend build did not produce static/frontend assets." >&2
    ls -la static/frontend 2>/dev/null || true
    exit 1
  fi
fi

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
