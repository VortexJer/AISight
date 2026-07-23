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

# A skill on disk is not enough: an agent only routes a request to it if the
# global instructions say so. That block is written here and removed on
# uninstall — fenced, so nothing outside the fence is ever touched. Whatever
# else lives in that file is the user's, and stays.
BEGIN = "<!-- solidsight:begin (managed by the solidsight package) -->"
END = "<!-- solidsight:end -->"
MEMORY_BLOCK = f"""{BEGIN}
# solidsight
- **solidsight** (`~/.claude/skills/solidsight/SKILL.md`) - any 3D
  design/CAD/3D-print request (parts, enclosures, mechanisms, assemblies).
  Trigger: `/solidsight`
When the user asks for a 3D model or types `/solidsight`, use the installed
solidsight skill before doing anything else. ALWAYS give the human their
preview without being asked: launch `solidsight view model.py` at the START
of the commission, before the model file even exists. And if the request
names a SPECIFIC real thing (a particular car, device, character) rather
than a generic object, ALWAYS ask the detail-mode question — representative
or detailed functional — before designing.
{END}"""


def default_skill_dir() -> Path:
    return Path.home() / ".claude" / "skills" / "solidsight"


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
        new = (old.rstrip() + "\n\n" if old.strip() else "") + \
            MEMORY_BLOCK + "\n"
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
    # only the real install owns the global routing note: a skill
    # copied somewhere else (tests, a sandbox) must never reach
    # into the user's ~/.claude and edit their instructions
    wrote = write_memory() if target is None else False
    if not quiet:
        print(f"solidsight skill v{__version__} installed at {dst}")
        if wrote:
            print(f"routing note written to {memory_file()}")
        print("Claude Code will use it for 3D design requests "
              "(new sessions pick it up automatically).")
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
    print("also removing the aisight umbrella (it requires solidsight) — "
          "the other tools stay")
    return subprocess.call([sys.executable, "-m", "pip", "uninstall",
                            "-y", "aisight"])


def uninstall(remove_package: bool = True) -> int:
    """Remove the skill directory, then pip-uninstall the package."""
    dst = default_skill_dir()
    if dst.exists():
        shutil.rmtree(dst)
        print(f"removed skill: {dst}")
    else:
        print(f"skill was not installed (nothing to remove at {dst})")
    if drop_memory():
        print(f"removed our routing note from {memory_file()}")
    if remove_package:
        print("removing the solidsight package...")
        code = subprocess.call([sys.executable, "-m", "pip", "uninstall",
                                "-y", "solidsight"])
        return _drop_umbrella() or code
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
        install_skill(quiet=True)   # the real one: it owns the routing note
        print(("solidsight: Claude Code skill installed at "
               if fresh else
               "solidsight: Claude Code skill updated at ") + str(dst),
              file=sys.stderr)
    except Exception:
        pass
