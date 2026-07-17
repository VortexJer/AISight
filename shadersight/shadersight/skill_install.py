"""Self-hosting of the Claude Code skill (same contract as solidsight)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from . import __version__

MARKER = ".installed-version"
SUBDIRS = ()


def default_skill_dir() -> Path:
    return Path.home() / ".claude" / "skills" / "shadersight"


def _source() -> Path:
    return Path(str(resources.files("shadersight") / "skill_data"))


def install_skill(target: Path | None = None, quiet: bool = False) -> Path:
    dst = Path(target) if target else default_skill_dir()
    src = _source()
    if not (src / "SKILL.md").exists():
        raise RuntimeError(
            f"packaged skill data missing at {src} — reinstall "
            "shadersight")
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
        print(f"shadersight skill v{__version__} installed at {dst}")
    return dst


def uninstall(remove_package: bool = True) -> int:
    dst = default_skill_dir()
    if dst.exists():
        shutil.rmtree(dst)
        print(f"removed skill: {dst}")
    else:
        print(f"skill was not installed (nothing at {dst})")
    if remove_package:
        print("removing the shadersight package...")
        return subprocess.call([sys.executable, "-m", "pip", "uninstall",
                                "-y", "shadersight"])
    return 0


def maybe_autoinstall() -> None:
    """Silent self-hosting; never raises — a failure here must not break
    an inspection."""
    try:
        if not (Path.home() / ".claude").is_dir():
            return
        dst = default_skill_dir()
        marker = dst / MARKER
        if dst.exists() and marker.exists() and \
                marker.read_text(encoding="utf-8").strip() == __version__:
            return
        fresh = not dst.exists()
        install_skill(dst, quiet=True)
        print(("shadersight: Claude Code skill installed at "
               if fresh else
               "shadersight: Claude Code skill updated at ") + str(dst),
              file=sys.stderr)
    except Exception:
        pass
