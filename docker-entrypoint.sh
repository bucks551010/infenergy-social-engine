#!/bin/sh
set -eu

mkdir -p "$DATA_DIR"
cp -an /app/data/. "$DATA_DIR/"

exec "$@"