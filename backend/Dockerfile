FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
# Зависимости, включая cuOpt, зависят только от pyproject.toml. Изменения в src
# не сбрасывают этот слой; кэш pip сохраняет скачанные пакеты между сборками.
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import pathlib, tomllib; project = tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]; pathlib.Path("/tmp/requirements.txt").write_text("\n".join(project["dependencies"] + project["optional-dependencies"]["solver"]) + "\n")' \
    && python -m pip install --extra-index-url https://pypi.nvidia.com -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY src ./src

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
