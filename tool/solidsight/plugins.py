"""Plugin system: extend solidsight without touching the core.

A plugin is any installed Python package that declares an entry point in
the group ``solidsight.plugins``::

    # pyproject.toml of the plugin package
    [project.entry-points."solidsight.plugins"]
    my_plugin = "my_plugin:register"

The target is a ``register(api)`` callable. The api object offers:

    api.add_exporter(name, fn)        # fn(scene, out_dir) -> list[str]
    api.add_validator(name, fn)       # fn(scene) -> list[check dicts]
    api.add_parts(namespace, {name: generator})

Custom exporters run when a build passes --plugin-exports; validators run
on every build. A crashing plugin NEVER crashes a build: its error
becomes a warning check and a bus event. `solidsight plugins` lists what
is installed. Example plugin: docs/plugins/example/ in the repository.
"""

from __future__ import annotations

from .events import BUS


class PluginAPI:
    def __init__(self, plugin_name: str):
        self.plugin = plugin_name
        self.exporters: dict[str, callable] = {}
        self.validators: dict[str, callable] = {}
        self.parts: dict[str, dict] = {}

    def add_exporter(self, name: str, fn) -> None:
        self.exporters[name] = fn

    def add_validator(self, name: str, fn) -> None:
        self.validators[name] = fn

    def add_parts(self, namespace: str, generators: dict) -> None:
        self.parts[namespace] = dict(generators)


_registry: list[PluginAPI] | None = None


def discover(refresh: bool = False) -> list[PluginAPI]:
    """Load every installed plugin exactly once; isolate failures."""
    global _registry
    if _registry is not None and not refresh:
        return _registry
    _registry = []
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="solidsight.plugins")
    except Exception:
        return _registry
    for ep in sorted(eps, key=lambda e: e.name):
        api = PluginAPI(ep.name)
        try:
            register = ep.load()
            register(api)
            _registry.append(api)
            BUS.emit("plugins", "info",
                     f"loaded '{ep.name}': "
                     f"{len(api.exporters)} exporter(s), "
                     f"{len(api.validators)} validator(s), "
                     f"{len(api.parts)} parts namespace(s)")
        except Exception as e:
            api.error = f"{type(e).__name__}: {e}"   # type: ignore
            _registry.append(api)
            BUS.warn("plugins", f"plugin '{ep.name}' failed to load: "
                                f"{api.error}")
    return _registry


def run_validators(scene) -> list[dict]:
    """Every plugin validator gets the scene; crashes become warnings."""
    checks: list[dict] = []
    for api in discover():
        for name, fn in api.validators.items():
            try:
                with BUS.stage("plugins", f"validator {api.plugin}.{name}"):
                    result = fn(scene) or []
                for c in result:
                    c.setdefault("level", "warn")
                    c.setdefault("id", f"plugin-{api.plugin}-{name}")
                    c["plugin"] = api.plugin
                    checks.append(c)
            except Exception as e:
                checks.append({
                    "level": "warn", "id": "plugin-error",
                    "plugin": api.plugin,
                    "message": f"plugin validator '{api.plugin}.{name}' "
                               f"crashed: {type(e).__name__}: {e}",
                    "suggestion": "a plugin failure never fails the build;"
                                  " fix or uninstall the plugin"})
    return checks


def run_exporters(scene, out_dir) -> list[str]:
    files: list[str] = []
    for api in discover():
        for name, fn in api.exporters.items():
            try:
                with BUS.stage("plugins", f"exporter {api.plugin}.{name}"):
                    files.extend(fn(scene, out_dir) or [])
            except Exception as e:
                BUS.warn("plugins", f"exporter '{api.plugin}.{name}' "
                                    f"crashed: {type(e).__name__}: {e}")
    return files
