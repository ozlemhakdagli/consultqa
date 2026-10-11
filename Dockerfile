# Builder: a virtualenv with CPU torch, the pinned requirements and the consultqa package.
FROM python:3.11.17-slim-trixie AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /build
COPY requirements.txt ./
# CPU torch comes first, so the pinned torch in requirements.txt is already satisfied.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 torchvision==0.29.1 \
 && pip install -r requirements.txt

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .

# Runtime: the virtualenv, the package and the model fetch script, run as a non-root user.
FROM python:3.11.17-slim-trixie AS runtime

RUN groupadd --gid 10001 consultqa \
 && useradd --uid 10001 --gid consultqa --no-create-home --home-dir /app --shell /usr/sbin/nologin consultqa \
 && mkdir -p /app/state /models \
 && chown consultqa:consultqa /app/state /models

COPY --from=builder /opt/venv /opt/venv
COPY scripts/fetch_models.py /app/scripts/fetch_models.py
COPY frontend /app/frontend

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    HF_HUB_OFFLINE=1 \
    CONSULTQA_DOCLING_ARTIFACTS=/models/docling \
    CONSULTQA_STATE_DIR=/app/state \
    CONSULTQA_FRONTEND_DIR=/app/frontend

WORKDIR /app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "consultqa.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
