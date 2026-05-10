FROM python:3.11-slim

WORKDIR /app

# git for cloning repos, curl for healthcheck
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install deps
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the fastembed model during build so first request isn't slow
# Model is cached inside the container image — no download at runtime
RUN python -c "from fastembed import TextEmbedding; list(TextEmbedding('BAAI/bge-small-en-v1.5').embed(['warmup']))"

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]