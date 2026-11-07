# syntax=docker/dockerfile:1.6
FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d AS d2-assets

# The immutable vendor archive is verified at build time; no unpinned fetch.
ADD --checksum=sha256:5669ddc46b99e942cc96078f4a4e36d5e62103348f4c05179ede27802fdd87a9 https://github.com/d2lang/d2/releases/download/v0.9.0/d2-v0.9.0-linux-amd64.tar.gz /tmp/d2-v0.9.0.tar.gz
RUN mkdir -p /opt/schauwerk/d2 \
    && tar -xzf /tmp/d2-v0.9.0.tar.gz -C /opt/schauwerk/d2 --strip-components=1 \
      d2-v0.9.0/bin/d2 \
      d2-v0.9.0/LICENSE.txt \
      d2-v0.9.0/THIRD_PARTY_NOTICES.txt \
    && chmod -R a+rX /opt/schauwerk/d2 \
    && /opt/schauwerk/d2/bin/d2 --version | grep -qx 'v0.9.0'

FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d

ARG VCS_REF=unknown
LABEL org.opencontainers.image.source="https://github.com/heimgewebe/schauwerk" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.title="Schauwerk Schaubild native runtime"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SCHAUWERK_D2_PREVIEW_BINARY=/opt/schauwerk/d2/bin/d2

WORKDIR /app
RUN mkdir -p \
      /app/src/schauwerk/visual \
      /app/src/schauwerk/resources/native_viewer \
      /app/src/schauwerk/resources/standalone_editor \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin schauwerk

COPY src/schauwerk/__init__.py /app/src/schauwerk/__init__.py
COPY src/schauwerk/visual/__init__.py \
     src/schauwerk/visual/grammar.py \
     src/schauwerk/visual/miro_dsl.py \
     src/schauwerk/visual/representation.py \
     src/schauwerk/visual/drawio_import.py \
     src/schauwerk/visual/json_fidelity.py \
     src/schauwerk/visual/grapheme.py \
     src/schauwerk/visual/native_canvas_smart_router.py \
     src/schauwerk/visual/native_diagram.py \
     src/schauwerk/visual/native_document.py \
     src/schauwerk/visual/native_viewer.py \
     src/schauwerk/visual/d2_preview.py \
     src/schauwerk/visual/standalone_editor.py \
     /app/src/schauwerk/visual/
COPY src/schauwerk/resources/__init__.py /app/src/schauwerk/resources/__init__.py
COPY src/schauwerk/resources/native_viewer/__init__.py \
     src/schauwerk/resources/native_viewer/assets.py \
     src/schauwerk/resources/native_viewer/smart_router.py \
     /app/src/schauwerk/resources/native_viewer/
COPY src/schauwerk/resources/standalone_editor/__init__.py \
     src/schauwerk/resources/standalone_editor/assets.py \
     src/schauwerk/resources/standalone_editor/representation_editor.py \
     /app/src/schauwerk/resources/standalone_editor/

RUN chmod -R a=rX /app/src

# The runtime image ships only D2 executable and license notices.
COPY --from=d2-assets /opt/schauwerk/d2/ /opt/schauwerk/d2/

USER 10001:10001
EXPOSE 8765

CMD ["python", "-m", "schauwerk.visual.standalone_editor", "serve", "--port", "8765"]
