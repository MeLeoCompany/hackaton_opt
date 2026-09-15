FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
# вместе с решателем cuOpt: его пакеты лежат на отдельном индексе NVIDIA
RUN pip install --no-cache-dir --extra-index-url https://pypi.nvidia.com ".[solver]"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
