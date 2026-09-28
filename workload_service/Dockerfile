FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py dashboard.py notifications.py logic.py snapshot.py /app/
ENV TZ=Europe/Warsaw PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/worker.py"]
CMD ["serve"]
