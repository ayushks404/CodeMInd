FROM python:3.11-slim

WORKDIR /app

# git for cloning repos, curl for healthcheck
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install deps — sentence-transformers will download the model at runtime (first run)
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model during build so first request isn't slow
# Model is cached at /root/.cache/torch/sentence_transformers/
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
