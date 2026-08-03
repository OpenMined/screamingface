"""Combine the hand-written `url4.toml` with generated `[data]` fragments, at image build.

    python -m url4_cloud.runner.merge_config \\
        --base url4.toml --fragment /opt/benchmarks/draco/url4.data.toml \\
        --out /etc/url4/url4.toml

WHY a merge step rather than `cat`: TOML admits a table name ONCE, so two `[data]` sections
cannot be concatenated, and a plain append cannot detect a generated route colliding with a
declared command or model. Both failures would surface at Job BOOT — after a client has already
minted a token and attached a WebSocket — instead of failing the build.

INVARIANT: the result is validated with the RUNNER's own parser (`runner.config.parse_config`),
not a lookalike. Anything this accepts, the Job accepts.

WHY this lives in `runner/` and not beside the benchmark generators: it validates the RUN MODE's
config, so it belongs to that half. `benchmarks/` is a shared leaf both halves may import, and a
leaf that imports `runner` would couple every module depending on it to the run mode — the
layering gate rejects exactly that. Nothing imports this at runtime; it is a build-step tool.

The base file's text is preserved verbatim so its comments — which carry the reasoning a reviewer
signed off on — survive into the shipped image. Only the combined `[data]` table is rendered.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from url4_cloud.runner.config import RunnerConfigError, parse_config


class MergeError(ValueError):
    """The fragments cannot be combined into a usable declared world."""


def merge(base_text: str, fragment_texts: Sequence[str]) -> str:
    """Return the merged TOML text. Raises :class:`MergeError` on anything unusable."""
    if not fragment_texts:
        return base_text

    base = _parse(base_text, "base config")
    claimed = _claimed_routes(base)
    data: dict[str, Any] = dict(base.get("data") or {})
    claimed |= set(data)

    for index, text in enumerate(fragment_texts):
        fragment = _parse(text, f"fragment {index}")
        unexpected = sorted(set(fragment) - {"data"})
        if unexpected:
            raise MergeError(
                f"fragment {index} declares {unexpected} — a generated fragment may declare "
                "only [data]; executable routes stay in the reviewed base config"
            )
        for path, spec in (fragment.get("data") or {}).items():
            if path in claimed:
                raise MergeError(f"{path!r} already declared — fragment {index} would shadow it")
            claimed.add(path)
            data[path] = spec

    merged = _strip_data_table(base_text) + "\n" + _render_data(data)
    _validate(merged)
    return merged


def _parse(text: str, label: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise MergeError(f"cannot parse {label}: {exc}") from None


def _claimed_routes(base: Mapping[str, Any]) -> set[str]:
    """Every path the base already owns — commands and aigateway model routes.

    A generated artifact route must not shadow one: `/read` and `/benchmark` are executable, and
    a model route is a public naming surface expressions depend on.
    """
    claimed = set(base.get("commands") or {})
    section = base.get("aigateway")
    if isinstance(section, Mapping):
        models = section.get("models") or []
        for entry in models:
            model_id = entry.get("id") if isinstance(entry, Mapping) else entry
            if model_id:
                claimed.add("/" + str(model_id).removeprefix("/"))
    return claimed


def _strip_data_table(base_text: str) -> str:
    """Drop the base's own ``[data]`` section — its entries are re-emitted in the merged table.

    Only a top-level ``[data]`` header starts the section; it ends at the next top-level header.
    """
    out: list[str] = []
    skipping = False
    for line in base_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and not stripped.startswith("[["):
            skipping = stripped == "[data]"
        if not skipping:
            out.append(line)
    return "".join(out).rstrip() + "\n"


def _render_data(data: Mapping[str, Any]) -> str:
    lines = [
        "# --- GENERATED — merged by url4_cloud.runner.merge_config. Do not edit. ---",
        f"# {len(data)} declared artifact(s). Regenerate by rebuilding the benchmark image.",
        "[data]",
    ]
    lines.extend(f'"{path}" = {_render_value(spec)}' for path, spec in sorted(data.items()))
    return "\n".join(lines) + "\n"


def _render_value(spec: Any) -> str:
    """Render one provider declaration back to TOML — containers here, scalars next door."""
    if isinstance(spec, Mapping):
        inner = ", ".join(f"{key} = {_render_value(value)}" for key, value in spec.items())
        return f"{{ {inner} }}"
    if isinstance(spec, (list, tuple)):
        return "[" + ", ".join(_render_value(v) for v in spec) + "]"
    return _render_scalar(spec)


def _render_scalar(spec: Any) -> str:
    # INVARIANT: bool before int — `bool` IS an `int` subclass, so the numeric branch would
    # render True as "1" and silently change a declared flag's type.
    if isinstance(spec, str):
        return _quote(spec)
    if isinstance(spec, bool):
        return "true" if spec else "false"
    if isinstance(spec, (int, float)):
        return str(spec)
    raise MergeError(f"cannot render {spec!r} as TOML")


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _validate(merged: str) -> None:
    """Parse the result with the RUNNER's parser — the point of the whole step."""
    raw = _parse(merged, "merged config")
    try:
        parse_config(raw, {})
    except RunnerConfigError as exc:
        raise MergeError(f"merged config is not a usable declared world: {exc}") from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="merge-config", description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--fragment", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        merged = merge(
            args.base.read_text(encoding="utf-8"),
            [path.read_text(encoding="utf-8") for path in args.fragment],
        )
    except (MergeError, OSError) as exc:
        print(f"merge failed: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(merged, encoding="utf-8")
    routes = len(tomllib.loads(merged).get("data") or {})
    print(f"merged {len(args.fragment)} fragment(s), {routes} data route(s) → {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - build-step entrypoint
    raise SystemExit(main())
