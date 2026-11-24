#!/bin/sh
set -eu
alembic upgrade head
if [ "${SKNET_CONNECTIVITY_MODE:-disabled}" != disabled ]; then
    exec python -m app.connectivity.supervise "$@"
fi
exec "$@"
