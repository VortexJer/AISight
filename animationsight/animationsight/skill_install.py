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


# A skill on disk is not enough: an agent only routes a request to it if the
# global instructions say so. That block is written here and removed on
# uninstall — fenced, so nothing outside the fence is ever touched. Whatever
# else lives in that file is the user's, and stays.
BEGIN = "<!-- animationsight:begin (managed by the animationsight package) -->"
END = "<!-- animationsight:end -->"
MEMORY_BLOCK = f"""{BEGIN}
- **animationsight** (`~/.claude/skills/animationsight/SKILL.md`) - review/debug OR EDIT animation clips or mocap (.bvh): foot sliding, pops, penetration, balance, loops;
  edit = parse_bvh -> modify -> save_bvh -> re-inspect. Trigger: `/animationsight`
When a request matches that domain — creating, reviewing or EDITING an
existing file — use the installed animationsight skill before doing anything else,
and end the commission's final run with `--show` so the human sees it.
{END}"""


def memory_file() -> Path:
    return Path.home() / ".claude" / "CLAUDE.md"


def write_memory(path: Path | None = None) -> bool:
    """Put our block in the global instructions. True if the file changed."""
    f = Path(path) if path else memory_file()
    if not f.parent.is_dir():          # no Claude Code here: write nothing
        return False
    old = f.read_text(encoding="utf-8") if f.exists() else ""
    if BEGIN in old and END in old:
        a, b = old.index(BEGIN), old.index(END) + len(END)
        new = old[:a] + MEMORY_BLOCK + old[b:]
    else:
        sep = "\n\n" if old.strip() else ""
        new = old.rstrip() + sep + MEMORY_BLOCK + "\n"
    if new == old:
        return False
    f.write_text(new, encoding="utf-8")
    return True


def drop_memory(path: Path | None = None) -> bool:
    """Take our block back out, leaving everything else exactly as it is."""
    f = Path(path) if path else memory_file()
    if not f.exists():
        return False
    old = f.read_text(encoding="utf-8")
    if BEGIN not in old or END not in old:
        return False               # hand-written mentions are not ours
    a, b = old.index(BEGIN), old.index(END) + len(END)
    new = (old[:a].rstrip() + "\n\n" + old[b:].lstrip()).strip()
    f.write_text(new + "\n" if new else "", encoding="utf-8")
    return True


def default_skill_dir() -> Path:
    return Path.home() / ".claude" / "skills" / "animationsight"


def _source() -> Path:
    return Path(str(resources.files("animationsight") / "skill_data"))


def install_skill(target: Path | None = None, quiet: bool = False) -> Path:
    dst = Path(target) if target else default_skill_dir()
    src = _source()
    if not (src / "SKILL.md").exists():
        raise RuntimeError(
            f"packaged skill data missing at {src} — reinstall "
            "animationsight")
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "SKILL.md", dst / "SKILL.md")
    for sub in SUBDIRS:
        sub_dst = dst / sub
        if sub_dst.exists():
            shutil.rmtree(sub_dst)
        if (src / sub).is_dir():
            shutil.copytree(src / sub, sub_dst)
    (dst / MARKER).write_text(__version__, encoding="utf-8")
    # only the real install owns the global routing note: a skill
    # copied somewhere else (tests, a sandbox) must never reach
    # into the user's ~/.claude and edit their instructions
    wrote = write_memory() if target is None else False
    if not quiet:
        print(f"animationsight skill v{__version__} installed at {dst}")
        if wrote:
            print(f"routing note written to {memory_file()}")
    return dst


def _installed(name: str) -> bool:
    """Is this distribution installed right now?"""
    from importlib.metadata import PackageNotFoundError, version
    try:
        version(name)
    except PackageNotFoundError:
        return False
    return True


def _drop_umbrella() -> int:
    """`pip install aisight` pulls the five tools in as dependencies, so
    removing one of them leaves the umbrella behind requiring a package
    that is gone — a broken install pip will complain about. The umbrella
    goes with it. The other four tools are untouched: pip does not
    cascade, and they were never aisight's to remove."""
    if not _installed("aisight"):
        return 0
    print("also removing the aisight umbrella (it requires animationsight) — "
          "the other tools stay")
    return subprocess.call([sys.executable, "-m", "pip", "uninstall",
                            "-y", "aisight"])


def uninstall(remove_package: bool = True) -> int:
    dst = default_skill_dir()
    if dst.exists():
        shutil.rmtree(dst)
        print(f"removed skill: {dst}")
    else:
        print(f"skill was not installed (nothing at {dst})")
    if drop_memory():
        print(f"removed our routing note from {memory_file()}")
    if remove_package:
        print("removing the animationsight package...")
        code = subprocess.call([sys.executable, "-m", "pip", "uninstall",
                                "-y", "animationsight"])
        return _drop_umbrella() or code
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
        install_skill(quiet=True)   # the real one: it owns the routing note
        print(("animationsight: Claude Code skill installed at "
               if fresh else
               "animationsight: Claude Code skill updated at ") + str(dst),
              file=sys.stderr)
    except Exception:
        pass
