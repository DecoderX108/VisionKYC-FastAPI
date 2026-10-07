FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY app ./app
ARG INSTALL_VISION=false
RUN if [ "$INSTALL_VISION" = "true" ]; then python -m pip install '.[vision]'; else python -m pip install .; fi
RUN useradd --uid 10001 --create-home kyc
USER kyc
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]

