#!/usr/bin/env bash
# exit on error
set -o errexit

python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

python manage.py collectstatic --no-input

# Run migrations (allow build to finish even if database connection is pending)
python manage.py migrate || true
