ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BUILD_COMMIT
ENV BUILD_COMMIT=$BUILD_COMMIT
USER root
COPY payload/requirements.txt /tmp/liftcontrol-required.txt
COPY wheels /tmp/liftcontrol-wheels
RUN python -c "from pathlib import Path; old=set(Path('/app/requirements.txt').read_text().splitlines()); new=set(Path('/tmp/liftcontrol-required.txt').read_text().splitlines()); assert old <= new and new-old <= {'reportlab==4.4.9'}, 'DEPENDENCIES_DIFFER_USE_FULL_UPDATE'" \
    && python -m pip install --no-index --no-deps --no-cache-dir /tmp/liftcontrol-wheels/reportlab-4.4.9-py3-none-any.whl \
    && python -m pip check \
    && cp /tmp/liftcontrol-required.txt /app/requirements.txt \
    && rm -rf /tmp/liftcontrol-wheels /tmp/liftcontrol-required.txt
COPY payload/fonts /usr/share/fonts/truetype/dejavu
RUN rm -rf /app/core /app/liftcontrol /app/templates /app/static/web
COPY --chown=10001:10001 payload/core /app/core
COPY --chown=10001:10001 payload/liftcontrol /app/liftcontrol
COPY --chown=10001:10001 payload/templates /app/templates
COPY --chown=10001:10001 payload/static /app/static
RUN DJANGO_DEBUG=True python manage.py collectstatic --noinput && chown -R 10001:10001 /app/staticfiles
USER 10001:10001
