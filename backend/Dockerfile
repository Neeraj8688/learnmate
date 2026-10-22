FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/.hf TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1
COPY requirements.txt .
# CPU-only torch keeps the image smaller
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt
# Pre-download the embedding model at build time (needs internet during build)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
COPY app ./app
EXPOSE 8000
# Hosts such as Render inject PORT (default 10000); locally we fall back to 8000.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
