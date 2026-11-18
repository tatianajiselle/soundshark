FROM ghcr.io/astral-sh/uv:0.13.8 AS uv

FROM python:3.14.7-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-editable

FROM python:3.14.7-slim-trixie
RUN useradd --create-home --uid 1000 soundshark
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./
COPY migrations ./migrations
RUN mkdir -p data/map && chown -R soundshark:soundshark data
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1
USER soundshark
VOLUME /app/data
ENTRYPOINT ["soundshark"]
CMD ["--help"]
