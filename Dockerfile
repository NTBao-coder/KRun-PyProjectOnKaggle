FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY krun ./krun
RUN python -m pip install .


FROM python:3.12-slim AS runtime

ARG USER_ID=1000
ARG GROUP_ID=1000

LABEL org.opencontainers.image.title="krun" \
      org.opencontainers.image.description="Run local Python projects on Kaggle" \
      org.opencontainers.image.source="https://github.com/nhminh107/KRun-PyProjectOnKaggle" \
      org.opencontainers.image.licenses="MIT"

ENV HOME=/home/krun \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN getent group "$GROUP_ID" >/dev/null || groupadd --gid "$GROUP_ID" krun \
    && useradd --uid "$USER_ID" --gid "$GROUP_ID" --create-home krun

COPY --from=builder /opt/venv /opt/venv

USER krun
WORKDIR /workspace

ENTRYPOINT ["krun"]
CMD ["--help"]
