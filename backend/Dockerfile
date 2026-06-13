ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

ARG APT_MIRROR_HOST=
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=
ARG PIP_TRUSTED_HOST=

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

WORKDIR /app

RUN set -eux; \
    if [ -n "${APT_MIRROR_HOST}" ] && [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|http://deb.debian.org/debian|https://${APT_MIRROR_HOST}/debian|g; s|http://security.debian.org/debian-security|https://${APT_MIRROR_HOST}/debian-security|g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -n "${APT_MIRROR_HOST}" ] && [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://deb.debian.org/debian|https://${APT_MIRROR_HOST}/debian|g; s|http://security.debian.org/debian-security|https://${APT_MIRROR_HOST}/debian-security|g" /etc/apt/sources.list; \
    fi; \
    printf 'Acquire::Retries "5";\nAcquire::https::Timeout "30";\nAcquire::http::Timeout "30";\n' > /etc/apt/apt.conf.d/99serenity-retries; \
    apt-get update; \
    apt-get install -y --no-install-recommends gcc libpq-dev; \
    groupadd --system app; \
    useradd --system --gid app --home-dir /app app; \
    chown app:app /app; \
    rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app backend/app ./app
COPY --chown=app:app backend/migrations ./migrations

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
