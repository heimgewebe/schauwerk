FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d

ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/heimgewebe/schauwerk" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Schauwerk Schaubild native runtime"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin schauwerk

USER 10001:10001
EXPOSE 8765

CMD ["python", "-m", "schauwerk.visual.standalone_editor", "serve", "--port", "8765"]
