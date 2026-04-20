"""JSON export renderer."""

from __future__ import annotations

from briefbridge.models.handoff import HandoffPack


def render_json(pack: HandoffPack) -> str:
    """Render a HandoffPack as pretty-printed JSON."""
    return pack.model_dump_json(indent=2)
