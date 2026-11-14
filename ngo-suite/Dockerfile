# NGO Suite in a container. Data lives in the /data volume (database, photos, backups).
FROM python:3.12-slim
WORKDIR /app
COPY . /app
ENV NGO_DB=/data/ngo.db NGO_FORCE_SECURE=1 PYTHONUNBUFFERED=1
EXPOSE 8000
# PORT is set by hosts such as Render; defaults to 8000 elsewhere
CMD ["sh", "-c", "python run.py --host 0.0.0.0 --port ${PORT:-8000}"]
