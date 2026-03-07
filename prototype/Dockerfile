FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir websockets

COPY knowledge.py monitor.py execution.py analysis.py planning.py config_example.py main.py ./

# ---------------------------------------------------------------------------

FROM base AS test

RUN pip install --no-cache-dir pytest pytest-asyncio

COPY pytest.ini ./
COPY tests/ ./tests/

CMD ["python", "-m", "pytest", "--tb=short", "-v"]

# ---------------------------------------------------------------------------

FROM base AS prod

CMD ["python", "main.py"]
