web: python manage.py migrate && gunicorn beness_backend.wsgi:application --bind 0.0.0.0:$PORT --timeout 600 --workers 2
