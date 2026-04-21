release: flask --app app db upgrade
web: gunicorn app:app --bind 0.0.0.0:$PORT
