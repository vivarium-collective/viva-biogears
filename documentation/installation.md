# Installation

BioGears has no PyPI release. It is built from source, unmodified, and driven through
pybiogears.

## Build BioGears and pybiogears

```bash
git clone https://github.com/vivarium-collective/pybiogears.git
cd pybiogears
scripts/install_biogears.sh        # BioGears 8.2.0 -> ~/biogears-8.2.0-install (about 20 min)
```

## Install viva-biogears

Clone viva-biogears next to pybiogears:

```bash
git clone https://github.com/vivarium-collective/viva-biogears.git
cd viva-biogears
uv venv --python 3.12 .venv && source .venv/bin/activate
CMAKE_PREFIX_PATH=~/biogears-8.2.0-install uv pip install '.[dev,engine]'
export BIOGEARS_RUNTIME=~/biogears-8.2.0-install/share/biogears/runtime
python -m pytest -q                # real engine; about 15 min
```

Install without `-e` to run the tests: process-bigraph finds `local:<module>.<Class>` classes through installed distributions, which list no editable package; `tests/test_compose_image.py` skips its engine tests on an editable install.

The `engine` extra builds pybiogears from GitHub at the commit this repository pins and
is tested with (`pyproject.toml`). Run the install again when that pin changes: its
workarounds are compiled code. After rebuilding or moving BioGears with the pin unchanged,
add `--refresh-package pybiogears`: uv otherwise reuses the pybiogears it built before.

`dev` includes the `workbench` extra: the web dashboard (`vivarium-workbench`, pinned to
0.3.92, since its later releases aren't installable from PyPI yet).

## Use viva-biogears from another project

Depend on `viva-biogears`, and on `viva-biogears[engine]` where the project runs the real
engine; BioGears itself is still built as above. The workbench is not a core dependency, so
your project keeps its own workbench version.

## Finding BioGears

`viva_biogears.runtime` uses the first of: the `runtime_dir` process config,
`$BIOGEARS_RUNTIME`, `~/biogears-8.2.0-install/share/biogears/runtime`. A location that is
given but isn't a BioGears runtime raises `BioGearsNotFoundError`; it never falls back.

## Build this documentation

```bash
make docs        # installs the docs group, runs every tutorial on the real engine, opens the site
```
