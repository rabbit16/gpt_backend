pkill -f gunicorn
gunicorn -w 1 -k uvicorn.workers.UvicornWorker main_app:app --bind 0.0.0.0:8888 --timeout 36