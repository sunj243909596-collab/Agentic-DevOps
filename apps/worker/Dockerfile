FROM python:3.12-slim

WORKDIR /app

# Install uv for dependency management
RUN pip install uv

# Copy workspace definition files
COPY pyproject.toml uv.lock ./
COPY apps/worker/ apps/worker/
COPY packages/ packages/

# Install the worker package and all dependencies
RUN uv sync --package devmanager-worker --no-dev

ENV PATH="/app/.venv/bin:$PATH"

CMD ["arq", "worker.main.WorkerSettings"]
