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
#
# Why exec: compose-api stops a run (time limit, scancel) with SIGTERM to the container, whose PID 1 under --compat is
# this script. The runner writes the rows it reached when it gets SIGTERM (only with COMPOSE_CHECKPOINT_SECONDS above 0,
# which compose-api's job sets from its checkpoint_seconds; with 0, PID 1 ignores SIGTERM), so it must be
# PID 1 itself: a shell running it as a child would end on the signal and leave it running unseen. exec means nothing
# here removes the scratch directory; it lives under TMPDIR (/tmp, which compose-api's job puts in its --workdir and
# removes when the job ends, as `docker run --rm` does with the container).
set -euo pipefail

: "${BIOGEARS_RUNTIME:=/opt/biogears/share/biogears/runtime}"
: "${COMPOSE_RUNNER:=/opt/runner.py}"
: "${COMPOSE_PYTHON:=/opt/venv/bin/python}"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/viva-biogears.XXXXXX")"

mkdir "$scratch/runtime"
shopt -s dotglob nullglob
for entry in "$BIOGEARS_RUNTIME"/*; do
  ln -s "$entry" "$scratch/runtime/$(basename "$entry")"
done

export BIOGEARS_RUNTIME="$scratch/runtime"
# viva_biogears.patients stabilizes a patient once and caches the state: not into the read-only image.
export VIVA_BIOGEARS_CACHE_DIR="${VIVA_BIOGEARS_CACHE_DIR:-$scratch/cache}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

exec "$COMPOSE_PYTHON" "$COMPOSE_RUNNER" "$@"
