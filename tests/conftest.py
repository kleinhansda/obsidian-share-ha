"""Lädt die HA-unabhängigen Module (vault, share_token, render) ohne Home Assistant.

Das Paket-__init__ importiert homeassistant; deshalb wird hier ein leeres
Platzhalter-Paket registriert und nur die reinen Module werden geladen.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

PKG = "obsidian_share"
SRC = Path(__file__).resolve().parent.parent / "custom_components" / PKG

pkg = types.ModuleType(PKG)
pkg.__path__ = [str(SRC)]
sys.modules.setdefault(PKG, pkg)


def _load(name: str):
    full = f"{PKG}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, SRC / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


for _name in ("vault", "share_token", "render"):
    _load(_name)
