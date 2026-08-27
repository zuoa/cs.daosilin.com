#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import time
from database import db
for i in range(40):
    try:
        db.connect(reuse_if_open=True)
        db.execute_sql('SELECT 1')
        print('database ready')
        break
    except Exception as e:
        print(f'wait db ({i+1}/40): {e}')
        time.sleep(1)
else:
    raise SystemExit('database timeout')
PY

echo "Initializing database..."
flask init-db

echo "Importing historical data when database is empty..."
flask import-history

echo "Starting scheduler..."
python scheduler.py &

echo "Starting Gunicorn..."
exec gunicorn -w 4 --bind 0.0.0.0:5001 app:app
