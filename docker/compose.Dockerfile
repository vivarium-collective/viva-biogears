# The viva-biogears image for compose-api (a prebuilt environment): BioGears 8.2.0 + pybiogears + viva-biogears +
# compose-api's generic runner, answering the job command
#   run /experiment/<doc> -o <out> -n <t>
# Design: docs/design/prebuilt-image.md. Build (from the repo root; linux/amd64 is the cluster's architecture):
#   docker build -f docker/compose.Dockerfile --build-arg PYBIOGEARS_SHA=<pyproject's pin> -t viva-biogears-compose .
#
# Both stages use one Ubuntu release, so the shared libraries BioGears was built against are the ones installed.
ARG UBUNTU=ubuntu:24.04

FROM ${UBUNTU} AS build
ARG PYBIOGEARS_SHA
RUN test -n "$PYBIOGEARS_SHA" || { echo "PYBIOGEARS_SHA build arg is required (the engine extra's commit in pyproject.toml)"; exit 1; }
# The Linux list at the top of pybiogears' scripts/install_biogears.sh, plus Python headers for pybiogears and `file`:
# BioGears' install step (CMake fixup_bundle) needs the `file` command, which a minimal Ubuntu image lacks; without it
# `cmake --install` fails with "fixup_bundle: not a valid bundle" (found building this image).
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates file cmake ninja-build g++ git xsdcxx libxerces-c-dev libeigen3-dev \
      libboost-dev libboost-system-dev libboost-filesystem-dev libboost-date-time-dev libboost-program-options-dev \
      python3 python3-dev python3-venv \
    && rm -rf /var/lib/apt/lists/*

# BioGears bakes its install prefix into a header, so the prefix is part of the image: /opt/biogears.
RUN git clone https://github.com/vivarium-collective/pybiogears.git /src/pybiogears \
    && git -C /src/pybiogears checkout "$PYBIOGEARS_SHA" \
    && /src/pybiogears/scripts/install_biogears.sh --prefix /opt/biogears --work /tmp/biogears-build \
    && rm -rf /tmp/biogears-build

RUN python3 -m venv /opt/venv
COPY docker/compose-constraints.txt /tmp/constraints.txt
RUN CMAKE_PREFIX_PATH=/opt/biogears /opt/venv/bin/pip install --no-cache-dir -c /tmp/constraints.txt /src/pybiogears
COPY . /src/viva-biogears
RUN /opt/venv/bin/pip install --no-cache-dir -c /tmp/constraints.txt /src/viva-biogears

FROM ${UBUNTU} AS runtime
ARG PYBIOGEARS_SHA
ARG VIVA_BIOGEARS_SHA=unknown
LABEL org.opencontainers.image.source="https://github.com/vivarium-collective/viva-biogears" \
      org.opencontainers.image.revision="${VIVA_BIOGEARS_SHA}" \
      io.github.vivarium-collective.pybiogears="${PYBIOGEARS_SHA}"
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 libxerces-c3.2t64 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/biogears /opt/biogears
COPY --from=build /opt/venv /opt/venv
COPY docker/runner.py /opt/runner.py
COPY docker/compose-entrypoint.sh /opt/compose-entrypoint.sh
ENV BIOGEARS_RUNTIME=/opt/biogears/share/biogears/runtime \
    OMP_NUM_THREADS=1 \
    PYTHONUNBUFFERED=1
ENTRYPOINT ["/opt/compose-entrypoint.sh"]
