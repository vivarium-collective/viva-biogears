# Prebuilt compose-api image for BioGears composites (design)

Status: **proposal, for review. No image is built by this PR.** Part of proving simulation-core
([inflect-sim-core](https://github.com/INFLECT-Praenora/inflect-sim-core)) on compose-api.

## Why an image

compose-api cannot run a BioGears composite today (per compose-api's maintainers, 2026-11-24):

1. Nothing for `biogears`, `viva_biogears` or `viva_simulation_core` is registered in its manifest/environments.
2. Its composed (pixi) environments install only conda and PyPI/git packages. pybiogears is not on PyPI and needs
   `find_package(Biogears)` against a source-built BioGears 8.2.0; BioGears is not on conda-forge.
3. The Dockerfiles in this repo and in inflect-sim-core serve the workbench (`uv sync`, port 9863). They contain no
   BioGears and do not answer compose-api's runner command line.

The route compose-api already supports for this is a **prebuilt environment**: an owner-published OCI image, pinned
by digest, named in `environments.yaml`. viva-pde-particle is the precedent
(`docker/compose.Dockerfile`, `.github/workflows/compose-image.yml`, image `ghcr.io/<owner>/viva-pde-particle-compose`).

Trade-off: a prebuilt run skips compose-api's per-class allow-list, so anything in the image can run. Acceptable for
trusted code in a trial; weaker than a composed registry entry.

## The contract the image must answer

compose-api's SLURM job runs (`compose_api/simulation/job_script.py`, read on origin/main):

```
singularity run --compat --env-file <pbg.env> --bind <dir>:/experiment <image> \
    run /experiment/<job>.<pbg|omex> -o /experiment/output -n <end_time>
```

then zips `/experiment/output`. So: the entrypoint takes `run <doc> -o <dir> -n <t>`; the image is read-only
(Apptainer `--compat`), with a writable `/tmp` and `/experiment`; results land in `<dir>` (`results_*.pber`).
Events: the job exports `PBG_TRACEPARENT` etc. in the env file; an engine that has process-bigraph events
(>= 1.8.5) picks them up, any other ignores them.

## Layers and owners

| Image | Owner repo | Contains |
|---|---|---|
| `ghcr.io/vivarium-collective/viva-biogears-compose` | **viva-biogears** (this repo) | stock BioGears 8.2.0 install + assembled runtime, pybiogears, viva-biogears, the runner entrypoint |
| `ghcr.io/inflect-praenora/inflect-sim-core-compose` | **inflect-sim-core** | `FROM` the viva-biogears image **by digest**, plus inflect-sim-core and its other pinned engines |

Naming follows `viva-pde-particle-compose`. linux/amd64 only (the cluster's architecture).

### viva-biogears image (base)

Multi-stage, one Debian/Ubuntu release in both stages so the runtime libraries (libxerces-c, libstdc++) match what
BioGears was built against:

1. **build**: apt deps from the header of pybiogears' `scripts/install_biogears.sh`, run it with a fixed
   `--prefix /opt/biogears` (BioGears bakes the prefix into a header, so the prefix is part of the image's identity),
   then build pybiogears against it. pybiogears CI (PR #4 on pybiogears) already does exactly this on
   ubuntu-24.04: cold build plus full suite took 16 min.
2. **runtime**: copy `/opt/biogears` and a venv holding pybiogears + viva-biogears (installed at the pinned commits).

Pins are build args, never `main`: `PYBIOGEARS_SHA` and `VIVA_BIOGEARS_SHA` (both from this repo's
`pyproject.toml`; a mismatched pair makes BioGears return NaN silently, per inflect-sim-core's README). The BioGears
commit is the one pinned in pybiogears' install script.

Environment baked in: `BIOGEARS_RUNTIME=/opt/biogears/share/biogears/runtime` (the order in
`viva_biogears/runtime.py`: config, `$BIOGEARS_RUNTIME`, default), `VIVA_BIOGEARS_CACHE_DIR=$TMPDIR/viva-biogears`
(stabilized-state cache must not write into the read-only image), `OMP_NUM_THREADS=1`.

### Entrypoint

`ENTRYPOINT ["/opt/compose-entrypoint.sh"]`: sets `TMPDIR`, `cd`s to a writable scratch directory (pybiogears'
save-to-bytes goes through a temp file in the working directory), then `exec`s the runner with `"$@"`.

Runner choice (**open question, see below**): the preferred option is to reuse compose-api's own generic runner,
`compose_api/environments/runner.py` (stdlib + process-bigraph only; written into every composed image; same
command line; `COMPOSE_RUNNER_TYPES` for type tables), vendored at a pinned compose-api commit with its sha256
checked in the Dockerfile. The alternative is a small `viva_biogears.compose_runner` like viva-pde-particle's.
Reusing avoids a second hand-rolled runner (it can only drift from the contract).

## Tests: real engine, no mocks

CI job (`.github/workflows/compose-image.yml`, modelled on viva-pde-particle's), on `ubuntu-latest`:

1. Build the image (amd64).
2. **docker**: run a short real composite (`biogears_hemorrhage`, ~10 s simulated) through the entrypoint and check
   the results file for finite, physiologically sensible vitals (non-NaN HR/MAP; the oracle is BioGears itself via
   the existing `tests/` checks, not a fixture).
3. **apptainer, the exact job contract** (`eWaterCycle/setup-apptainer`): `apptainer run --compat --bind exp:/experiment
   image.sif run /experiment/experiment.pbg -o /experiment/output -n 10`, then assert `results_*.pber` exists with
   finite vitals. This is what proves the read-only image works: it will surface any write into the install tree.
4. Assert the image does not import the workbench (`import vivarium_workbench` fails), as viva-pde-particle does.
5. Push `:sha-<short>` (and `:latest` on main) only after 2 to 4 pass; record the digest.

What these prove: the image answers the contract and the engine runs in it. What they leave unproven: behaviour on
compose-api's cluster (resources, `--workdir`), which only a real submission shows.

## Digest and registration

The pushed digest (`sha256:...`) is the contract. compose-api registers the image by digest, never by tag
(`environments create ... --image <digest>`). viva-biogears CI prints the digest in the job summary; a release of the
image is a git tag on this repo, and the compose-api version note names that tag.

## compose-api side (owned by compose-api-supervisor, nothing here changes compose-api)

One `kind: prebuilt` environment in `environments.yaml` for the inflect-sim-core image (and optionally one for the
base), a compliance case (one short real sepsis or hemorrhage run), and a compose-api release. Each compose-api change
is confirmed with Alex by that session before it starts. The registered environment is then used with
`compose-api run doc.pbg --simulator <env>`.

## Known gaps this will measure (input to the later dedicated-compute case)

Per compose-api's code: every run is a batch SLURM job (no live session), 2 CPU / 8 GB per job, simulated time
capped at 1,000 s (24 h with the long-runs role), results when the job ends, container start-up on every run.
BioGears runs about real-time-multiple fast enough for short runs; 48 h sepsis arms (about 8 h wall each) do not fit
12 h wall comfortably. The trial documents what actually happens.

## Open questions

1. Runner: vendor compose-api's generic `runner.py` (pinned commit + sha256) or ship our own module? (compose-api maintainers)
2. Does BioGears write into its runtime directory on `load_state`/`initialize`? The apptainer test in CI answers this;
   if yes, the runtime must be copied to `$TMPDIR` at start (cost: size of the data directory).
3. Which Python: both repos require >= 3.12; pybiogears CI uses 3.12. Pin 3.12 in the image unless Arnab prefers otherwise.
4. Who may push to `ghcr.io/vivarium-collective` from this repo's Actions (package Actions access; viva-pulse hit a
   push denial after its repo transfer).
5. Image size and cold-build time on `ubuntu-latest` (not measured; pybiogears CI built BioGears in under 16 min on the
   same runner class).
