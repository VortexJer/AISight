"""Self-hosting of the Claude Code skill.

The SKILL.md + references/ + domains/ ship inside the pip package
(skill_data/). On the first CLI run on a machine that has Claude Code
(~/.claude exists), the skill installs itself into
~/.claude/skills/solidsight and keeps itself up to date on version
changes. `solidsight uninstall` removes the skill AND the pip package.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from . import __version__

MARKER = ".installed-version"
SUBDIRS = ("references", "domains")


def default_skill_dir() -> Path:
    return Path.home() / ".claude" / "skills" / "solidsight"


def _source() -> Path:
    return Path(str(resources.files("solidsight") / "skill_data"))


def install_skill(target: Path | None = None, quiet: bool = False) -> Path:
    """Copy SKILL.md + references/ + domains/ into the Claude Code skills
    directory."""
    dst = Path(target) if target else default_skill_dir()
    src = _source()
    if not (src / "SKILL.md").exists():
        raise RuntimeError(
            f"packaged skill data missing at {src} — reinstall solidsight")
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "SKILL.md", dst / "SKILL.md")
    for sub in SUBDIRS:
        sub_dst = dst / sub
        if sub_dst.exists():
            shutil.rmtree(sub_dst)
        if (src / sub).is_dir():
            shutil.copytree(src / sub, sub_dst)
    (dst / MARKER).write_text(__version__, encoding="utf-8")
    if not quiet:
        print(f"solidsight skill v{__version__} installed at {dst}")
        print("Claude Code will use it for 3D design requests "
              "(new sessions pick it up automatically).")
    return dst


def uninstall(remove_package: bool = True) -> int:
    """Remove the skill directory, then pip-uninstall the package."""
    dst = default_skill_dir()
    if dst.exists():
        shutil.rmtree(dst)
        print(f"removed skill: {dst}")
    else:
        print("skill was not installed (nothing to remove at "
              f"{dst})")
    if remove_package:
        print("removing the solidsight package...")
        return subprocess.call([sys.executable, "-m", "pip", "uninstall",
                                "-y", "solidsight"])
    return 0


def maybe_autoinstall() -> None:
    """Silent self-hosting: runs at the start of every CLI invocation.

    - does nothing unless ~/.claude exists (i.e. Claude Code is present)
    - installs the skill if missing, refreshes it if the version changed
    - never raises: a failure here must not break a build
    """
    try:
        claude_home = Path.home() / ".claude"
        if not claude_home.is_dir():
            return
        dst = default_skill_dir()
        marker = dst / MARKER
        if dst.exists() and marker.exists() and \
                marker.read_text(encoding="utf-8").strip() == __version__:
            return
        fresh = not dst.exists()
        install_skill(dst, quiet=True)
        print(("solidsight: Claude Code skill installed at "
               if fresh else
               "solidsight: Claude Code skill updated at ") + str(dst),
              file=sys.stderr)
    except Exception:
        pass
