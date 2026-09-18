FROM eclipse-temurin:21-jre-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt
# r5py обычно скачивает JAR при первом import. Запекаем проверенный по SHA-256 JAR
# в образ, чтобы рабочий запуск не зависел от доступа к GitHub.
RUN python3 -c "import r5py; print(r5py.__version__)"

COPY app ./app

EXPOSE 8003
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
