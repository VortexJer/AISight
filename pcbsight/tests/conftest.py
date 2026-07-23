"""Test isolation.

The CLIs self-host their skill: any invocation installs it into
~/.claude/skills and writes a routing note into ~/.claude/CLAUDE.md. That
is right on a user's machine and wrong in a test run — a suite that edits
the developer's own Claude Code setup has reached outside its sandbox,
and it did: a run of these tests reinstalled skills that had been
deliberately removed.

So every test process, and every subprocess it spawns, gets a throwaway
home. Path.home() reads USERPROFILE on Windows and HOME elsewhere, so
both are set.
"""

import os
import pathlib
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _sandbox_home():
    with tempfile.TemporaryDirectory(prefix="aisight-test-home-") as home:
        keep = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
        os.environ["HOME"] = home
        os.environ["USERPROFILE"] = home
        # subprocesses must find the package from the checkout: a suite that
        # only passes when the tool happens to be pip-installed is testing
        # the machine, not the code
        root = str(pathlib.Path(__file__).resolve().parents[1])
        prev_path = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = (root + os.pathsep + prev_path
                                    if prev_path else root)
        try:
            yield home
        finally:
            if prev_path is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = prev_path
            for k, v in keep.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
