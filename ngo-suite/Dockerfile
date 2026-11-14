# NGO Suite in a container. Data lives in the /data volume (database, photos, backups).
FROM python:3.12-slim
WORKDIR /app
COPY . /app
ENV NGO_DB=/data/ngo.db NGO_FORCE_SECURE=1 PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]
