"""
tests/test_bug7_init_exports.py

Bug 7: orbitval/__init__.py had no exports. The documented import path
`from orbitval import TestRunner` (used in TEMPLATES.md, MAP.md, and
INTERNALS.md harness usage examples) raised ImportError.

Fix: __init__.py now exports TestRunner via a top-level import.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTopLevelImport:
    def test_from_orbitval_import_testrunner(self):
        """The documented import path must work without error."""
        from orbitval import TestRunner
        assert TestRunner is not None

    def test_imported_testrunner_is_the_real_class(self):
        """The exported TestRunner must be the same class as the one in runner.py."""
        from orbitval import TestRunner as TopLevel
        from orbitval.engine.runner import TestRunner as Direct
        assert TopLevel is Direct

    def test_all_exports_declared(self):
        """__all__ must include TestRunner so `from orbitval import *` works."""
        import orbitval
        assert hasattr(orbitval, "__all__")
        assert "TestRunner" in orbitval.__all__

    def test_version_still_accessible(self):
        """__version__ must still be accessible after adding the export."""
        import orbitval
        assert orbitval.__version__ == "0.1.0"

    def test_testrunner_is_instantiable_via_top_level_import(self):
        """TestRunner imported from orbitval must be instantiable (not a stub)."""
        from orbitval import TestRunner
        from pathlib import Path
        satellite_yaml = str(Path(__file__).parent.parent / "satellite.yaml")
        runner = TestRunner(
            config=satellite_yaml,
            autonomy=None,
            tle_line1="1 25544U 98067A   24010.50000000  .00016717  00000-0  10270-3 0  9007",
            tle_line2="2 25544  51.6400 208.9163 0006317  69.9862  25.2906 15.49815747 33333",
            duration_hours=0.1,
            step_seconds=60.0,
            seed=42,
        )
        assert runner.hardware is not None
