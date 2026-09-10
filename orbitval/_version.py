"""Single source of truth for the OrbitVal version.

Kept in its own module with no imports so that setuptools can read it
statically (pyproject: `version = {attr = "orbitval._version.__version__"}`)
and so that every runtime consumer — the CLI banner, the Celestrak
User-Agent, and the ORF report's orbitval_version field — reports the
same string without a manual multi-file bump.

Deliberately NOT importlib.metadata: that reads *installed* metadata,
which goes stale against an editable checkout and would silently stamp
reports with the wrong version.
"""

__version__ = "1.1.1"
