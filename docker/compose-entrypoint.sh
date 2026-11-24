#!/usr/bin/env bash
# Entrypoint of the viva-biogears compose-api image: answers compose-api's job command
#
#   singularity run --compat --workdir <w> --bind <dir>:/experiment <image> run /experiment/<doc> -o <out> -n <t>
#
# by running compose-api's own generic runner (docker/runner.py, vendored) on the real BioGears engine.
#
# Why a scratch runtime: pybiogears writes short-lived files (actions, conditions, configuration, saved states) into
# the engine's working directory, which viva-biogears sets to the BioGears runtime directory (pybiogears
# src/cpp/BioGearsThunk.cpp, temp_path()). The runtime is part of the read-only image, so the engine works in a
# scratch directory of symlinks to it: reads reach the image, new files land in the scratch directory. Measured:
# a read-only copy of the runtime fails on the first action; this layout passes.
set -euo pipefail

: "${BIOGEARS_RUNTIME:=/opt/biogears/share/biogears/runtime}"
: "${COMPOSE_RUNNER:=/opt/runner.py}"
: "${COMPOSE_PYTHON:=/opt/venv/bin/python}"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/viva-biogears.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

mkdir "$scratch/runtime"
shopt -s dotglob nullglob
for entry in "$BIOGEARS_RUNTIME"/*; do
  ln -s "$entry" "$scratch/runtime/$(basename "$entry")"
done

export BIOGEARS_RUNTIME="$scratch/runtime"
# viva_biogears.patients stabilizes a patient once and caches the state: not into the read-only image.
export VIVA_BIOGEARS_CACHE_DIR="${VIVA_BIOGEARS_CACHE_DIR:-$scratch/cache}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

rc=0
"$COMPOSE_PYTHON" "$COMPOSE_RUNNER" "$@" || rc=$?
exit "$rc"
