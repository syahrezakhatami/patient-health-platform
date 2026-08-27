#!/usr/bin/env python3
"""Generate TypeScript interfaces from openapi/iam-shell.json.

    python3 scripts/generate_iam_types.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

OPENAPI = Path(__file__).resolve().parents[1] / "openapi" / "iam-shell.json"
OUT = Path(__file__).resolve().parents[1] / "src" / "api" / "generated" / "iam-shell.ts"

HEADER = '''\
/**
 * Generated from frozen FastAPI source OpenAPI (openapi/iam-shell.json).
 *
 * Regenerate / drift-check:
 *   python3 scripts/export_iam_openapi.py
 *   python3 scripts/generate_iam_types.py
 *   python3 scripts/export_iam_openapi.py --check
 *   python3 scripts/generate_iam_types.py --check
 *
 * Do not hand-edit to invent fields. extra=forbid on the backend.
 */
'''


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _ts(schema: dict) -> str:
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    if "anyOf" in schema:
        return " | ".join(_ts(option) for option in schema["anyOf"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    json_type = schema.get("type")
    if json_type == "string":
        return "string"
    if json_type == "boolean":
        return "boolean"
    if json_type == "integer" or json_type == "number":
        return "number"
    if json_type == "null":
        return "null"
    if json_type == "array":
        return f"Array<{_ts(schema.get('items', {}))}>"
    if json_type == "object":
        return "Record<string, unknown>"
    return "unknown"


def render() -> str:
    document = json.loads(OPENAPI.read_text())
    schemas: dict = document["components"]["schemas"]
    parts = [HEADER]
    for name, schema in schemas.items():
        if schema.get("enum"):
            parts.append(f"export type {name} = {_ts(schema)};\n")
            continue
        required = set(schema.get("required") or [])
        properties = schema.get("properties") or {}
        lines = [f"export interface {name} {{"]
        for prop, prop_schema in properties.items():
            optional = "?" if prop not in required else ""
            lines.append(f"  {prop}{optional}: {_ts(prop_schema)};")
        lines.append("}")
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != rendered:
            raise SystemExit(f"Type drift: {OUT} does not match openapi/iam-shell.json")
        print(f"ok {OUT}")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(rendered)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
