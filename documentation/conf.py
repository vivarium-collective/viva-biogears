"""Sphinx configuration for the viva-biogears user documentation.

Build with `make docs` from the repo root. Tutorials are notebooks written in MyST
markdown and executed against the real BioGears engine during the build, in this
project's venv (the only environment with pybiogears); a cell that raises fails the build.

On Read the Docs, which can't build BioGears, the tutorials are published as code only and
the pages tagged ``hosted`` say so; every other page builds as it does locally."""
import os
from importlib.metadata import version as _version

project = "viva-biogears"
author = "Arnab Mutsuddy"
copyright = "2026, Arnab Mutsuddy. BioGears: Applied Research Associates (Apache 2.0)"
release = _version("viva-biogears")
version = release

extensions = ["myst_nb", "sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx.ext.viewcode"]
exclude_patterns = ["_build", "jupyter_execute", "Thumbs.db", ".DS_Store", "**/_*.md"]

default_role = "literal"  # the docstrings write `name` for code
autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = False  # the docstrings use numpy-style sections

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3
nb_execution_mode = "force"  # every build runs every tutorial against the current code and engine
nb_execution_raise_on_error = True
nb_execution_timeout = 1200
nb_execution_show_tb = True
if os.environ.get("READTHEDOCS") == "True":
    nb_execution_excludepatterns = ["tutorials/*"]
    tags.add("hosted")  # noqa: F821 (Sphinx provides `tags` to conf.py)

html_theme = "furo"
html_title = f"viva-biogears {release}"
