FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY workload_service/requirements.txt /app/workload_service/requirements.txt
RUN pip install --no-cache-dir -r workload_service/requirements.txt
COPY config.json /app/
COPY workload/logic.py workload/snapshot.py /app/workload/
COPY workload_service/worker.py workload_service/dashboard.py workload_service/notifications.py /app/workload_service/
ENV TZ=Europe/Warsaw PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/workload_service/worker.py"]
CMD ["serve"]
