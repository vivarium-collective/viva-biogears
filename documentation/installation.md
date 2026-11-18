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
uv pip install -e '.[dev]'
CMAKE_PREFIX_PATH=~/biogears-8.2.0-install uv pip install ../pybiogears
export BIOGEARS_RUNTIME=~/biogears-8.2.0-install/share/biogears/runtime
python -m pytest -q                # real engine; about 15 min
```

Reinstall pybiogears whenever you pull it: its workarounds are compiled code.

## Finding BioGears

`viva_biogears.runtime` uses the first of: the `runtime_dir` process config,
`$BIOGEARS_RUNTIME`, `~/biogears-8.2.0-install/share/biogears/runtime`. A location that is
given but isn't a BioGears runtime raises `BioGearsNotFoundError`; it never falls back.

## Build this documentation

```bash
make docs        # installs the docs group, runs every tutorial on the real engine, opens the site
```
