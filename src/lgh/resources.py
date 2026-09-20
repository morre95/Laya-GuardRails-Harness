from __future__ import annotations

from importlib.resources import files


def read_package_text(*parts: str) -> str:
    node = files("lgh")
    for part in parts:
        node = node.joinpath(part)
    return node.read_text(encoding="utf-8")
