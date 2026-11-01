# One image, two Cloud Run services: api (default CMD) and worker (uvicorn app.worker:app).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models
WORKDIR /app

# CPU-only torch keeps the image ~2 GB smaller than the default CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt && python -m spacy download en_core_web_sm

# Bake the embedding models into the image so cold starts never download them.
RUN python -c "from sentence_transformers import SentenceTransformer as S; \
S('sentence-transformers/all-MiniLM-L6-v2'); S('sentence-transformers/clip-ViT-B-32')"
ENV HF_HUB_OFFLINE=1

COPY app ./app
RUN useradd --uid 10001 --no-create-home app
USER app

ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
