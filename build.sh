#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "==> Upgrading pip and installing production dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Collecting static files with WhiteNoise..."
python manage.py collectstatic --noinput

echo "==> Applying database migrations..."
python manage.py migrate --noinput

echo "==> Build completed successfully!"
