ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BUILD_COMMIT
ENV BUILD_COMMIT=$BUILD_COMMIT
USER root
COPY payload/requirements.txt /tmp/liftcontrol-required.txt
RUN python -c "from pathlib import Path; assert Path('/app/requirements.txt').read_bytes()==Path('/tmp/liftcontrol-required.txt').read_bytes(), 'DEPENDENCIES_DIFFER_USE_FULL_UPDATE'" && rm /tmp/liftcontrol-required.txt
RUN rm -rf /app/core /app/liftcontrol /app/templates /app/static/web
COPY --chown=10001:10001 payload/core /app/core
COPY --chown=10001:10001 payload/liftcontrol /app/liftcontrol
COPY --chown=10001:10001 payload/templates /app/templates
COPY --chown=10001:10001 payload/static /app/static
RUN DJANGO_DEBUG=True python manage.py collectstatic --noinput && chown -R 10001:10001 /app/staticfiles
USER 10001:10001
