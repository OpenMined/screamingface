"""Built-in admin endpoints attached to every SF app.

Pulled out of ``core/app.py`` so :func:`create_app` stays focused on
wiring registries + lifespan. Endpoints exposed:

- ``GET  /health`` — liveness probe
- ``GET  /system/processes`` — process names visible to the server
- ``GET  /plugins`` — active plugin metadata
- ``GET  /plugins/{name}/schema`` — JSON Schema for a plugin's settings
- ``GET  /plugins/{name}/settings`` — current resolved settings (re-reads sf.json)
- ``POST /plugins/{name}/settings`` — update in-memory settings
- ``POST /plugins/{name}/settings/validate`` — dry-run settings validation
- ``POST /config/validate`` — diff/validate a proposed sf.json
"""

from __future__ import annotations

import logging
import subprocess

from fastapi import FastAPI, HTTPException, Request

from screamingface.plugin import Plugin

logger = logging.getLogger(__name__)


def _get_process_names() -> list[str]:
    """Return sorted unique names of currently running processes."""
    try:
        out = subprocess.check_output(["ps", "-eo", "comm="], text=True, timeout=5)
    except Exception:
        return []
    names: set[str] = set()
    for line in out.splitlines():
        name = line.strip().rsplit("/", 1)[-1]
        if name and not name.startswith("-"):
            names.add(name)
    return sorted(names)


def _inject_tag_enums(schema: dict, active_plugins: dict[str, Plugin]) -> None:
    """Walk a JSON Schema and inject ``enum`` for fields whose name matches a plugin tag.

    Convention: if a string property's name matches a known tag (e.g.
    ``"frontend"``), the enum is set to the list of active plugin names
    carrying that tag. Operates in-place on ``schema`` (incl. ``$defs``).
    """
    tag_map: dict[str, list[str]] = {}
    for p in active_plugins.values():
        for tag in p.tags:
            tag_map.setdefault(tag, []).append(p.name)
    if not tag_map:
        return

    def _walk(node: dict) -> None:
        for field_name, field_schema in node.get("properties", {}).items():
            if field_schema.get("type") == "string" and field_name in tag_map:
                field_schema["enum"] = tag_map[field_name]
            if field_schema.get("type") == "object":
                _walk(field_schema)
            items = field_schema.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                _walk(items)
        for defn in node.get("$defs", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)
        for defn in node.get("definitions", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)

    _walk(schema)


def _collapse_nullable(schema: dict) -> None:
    """Collapse ``anyOf: [{type: T}, {type: "null"}]`` to ``{type: T}``.

    Pydantic emits this pattern for ``X | None`` fields. RJSF treats
    ``anyOf`` as a type-selector dropdown, which is confusing for
    simple nullable scalars; collapsing gives RJSF a plain typed
    field.
    """

    def _walk(node: dict) -> None:
        for field_schema in node.get("properties", {}).values():
            any_of = field_schema.get("anyOf")
            if isinstance(any_of, list) and len(any_of) == 2:
                non_null = [s for s in any_of if s.get("type") != "null"]
                if len(non_null) == 1:
                    del field_schema["anyOf"]
                    field_schema.update(non_null[0])
            if field_schema.get("type") == "object":
                _walk(field_schema)
            items = field_schema.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                _walk(items)
        for defn in node.get("$defs", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)
        for defn in node.get("definitions", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)

    _walk(schema)


def _inject_examples(schema: dict, field_name: str, examples: list[str]) -> None:
    """Inject ``examples`` into string fields matching *field_name*.

    Uses JSON Schema ``examples`` (not ``enum``) so the value is a
    suggestion, not a strict constraint.
    """

    def _walk(node: dict) -> None:
        for fname, fschema in node.get("properties", {}).items():
            if fschema.get("type") == "string" and fname == field_name:
                fschema["examples"] = examples
            if fschema.get("type") == "object":
                _walk(fschema)
            items = fschema.get("items")
            if isinstance(items, dict) and items.get("type") == "object":
                _walk(items)
        for defn in node.get("$defs", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)
        for defn in node.get("definitions", {}).values():
            if isinstance(defn, dict) and defn.get("type") == "object":
                _walk(defn)

    _walk(schema)


def register_admin_routes(app: FastAPI) -> None:
    """Attach the built-in admin/diagnostic endpoints to ``app``.

    Reads registries off ``app.state``; the caller must populate it
    (``state.plugins`` etc.) before serving requests.
    """

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/system/processes")
    async def list_processes() -> list[str]:
        return _get_process_names()

    @app.get("/plugins")
    async def list_plugins() -> dict:
        return {
            name: {
                "version": p.version,
                "description": p.description,
                "has_settings": p.settings_class is not None,
                "requires_root": p.requires_root,
                "depends": p.depends,
                "conflicts": p.conflicts,
                "tags": p.tags,
            }
            for name, p in app.state.plugins.active_plugins.items()
        }

    @app.get("/plugins/{name}/schema")
    async def plugin_schema(name: str) -> dict:
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin:
            raise HTTPException(404, f"Plugin {name!r} not active")
        if not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} has no configurable settings")
        schema = plugin.settings_class.model_json_schema()
        _collapse_nullable(schema)
        _inject_tag_enums(schema, app.state.plugins.active_plugins)
        _inject_examples(schema, "process_filter", _get_process_names())
        return plugin.customize_schema(schema)

    @app.get("/plugins/{name}/settings")
    async def plugin_settings(name: str) -> dict:
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin or not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} not found or has no settings")
        from screamingface.core.config import load_config

        fresh_config = load_config()
        raw = fresh_config.plugin_config.get(name, {})
        try:
            return plugin.settings_class(**raw).model_dump()
        except Exception:
            if not plugin.settings:
                raise HTTPException(404, f"Plugin {name!r} has no settings") from None
            return plugin.settings.model_dump()

    @app.post("/plugins/{name}/settings")
    async def update_plugin_settings(name: str, request: Request) -> dict:
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin or not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} not found or has no settings")
        data = await request.json()
        plugin.settings = plugin.settings_class(**data)
        app.state.config.plugin_config[name] = data
        return plugin.settings.model_dump()

    @app.post("/plugins/{name}/settings/validate")
    async def validate_plugin_settings(name: str, request: Request) -> dict:
        plugin = app.state.plugins.active_plugins.get(name)
        if not plugin:
            raise HTTPException(404, f"Plugin {name!r} not active")
        if not plugin.settings_class:
            raise HTTPException(404, f"Plugin {name!r} has no configurable settings")
        body = await request.json()
        try:
            plugin.settings_class(**body)
            return {"valid": True}
        except Exception as exc:
            raise HTTPException(422, detail=str(exc)) from exc

    @app.post("/config/validate")
    async def validate_config(request: Request) -> dict:
        body = await request.json()
        proposed: list[str] = body.get("plugins", [])
        current: list[str] = body.get("current_plugins", [])
        errors: list[dict[str, str]] = []
        added = set(proposed) - set(current)
        discovered = app.state.plugins.discovered_plugins
        for name in added:
            if name not in discovered:
                errors.append({"plugin": name, "error": f"Plugin {name!r} is not installed."})
                continue
            try:
                instance = app.state.plugins.load_plugin(name)
            except Exception as exc:
                errors.append({"plugin": name, "error": f"Failed to load {name!r}: {exc}"})
                continue
            ok, reason = instance.preflight()
            if not ok:
                errors.append({"plugin": name, "error": reason})
                continue
            for conflict in instance.conflicts:
                if conflict in proposed:
                    errors.append(
                        {
                            "plugin": name,
                            "error": (
                                f"Conflicts with {conflict!r} — only one can be active at a time."
                            ),
                        }
                    )
        if errors:
            return {"valid": False, "errors": errors}
        return {"valid": True}
