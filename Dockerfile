# syntax=docker/dockerfile:1.6
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
      /app/src/schauwerk/resources/native_offline_html \
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
     src/schauwerk/visual/native_offline_html.py \
     src/schauwerk/visual/d2_preview.py \
     src/schauwerk/visual/standalone_editor.py \
     /app/src/schauwerk/visual/
COPY src/schauwerk/resources/__init__.py /app/src/schauwerk/resources/__init__.py
COPY src/schauwerk/resources/native_viewer/__init__.py \
     src/schauwerk/resources/native_viewer/assets.py \
     src/schauwerk/resources/native_viewer/hybrid_preview.py \
     src/schauwerk/resources/native_viewer/smart_router.py \
     /app/src/schauwerk/resources/native_viewer/
COPY src/schauwerk/resources/native_offline_html/__init__.py \
     src/schauwerk/resources/native_offline_html/assets.py \
     /app/src/schauwerk/resources/native_offline_html/
COPY src/schauwerk/resources/standalone_editor/__init__.py \
     src/schauwerk/resources/standalone_editor/assets.py \
     src/schauwerk/resources/standalone_editor/representation_editor.py \
     /app/src/schauwerk/resources/standalone_editor/

RUN chmod -R a=rX /app/src

# Reuse precisely the D2 v0.9.0 executable/notices from an accepted,
# source-verified Schauwerk release; GitHub's archive CDN returned 504 HTML
# instead of the expected sha256:5669dd... bytes in multiple OCI rebuilds.
# The exact OCI digest pins all bytes; no mutable vendor tag or download.
COPY --from=ghcr.io/heimgewebe/schauwerk-schaubild@sha256:a0f29a13e86244654afdeafb7b900357b8af29bd802b6fae374ca1f7f0b94597 \
     /opt/schauwerk/d2/ /opt/schauwerk/d2/
RUN /opt/schauwerk/d2/bin/d2 --version | grep -qx 'v0.9.0' \
    && test -s /opt/schauwerk/d2/LICENSE.txt \
    && test -s /opt/schauwerk/d2/THIRD_PARTY_NOTICES.txt

USER 10001:10001
EXPOSE 8765

CMD ["python", "-m", "schauwerk.visual.standalone_editor", "serve", "--port", "8765"]
