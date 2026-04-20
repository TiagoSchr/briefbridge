"""Handoff generation, export, and use service."""

from __future__ import annotations

from pathlib import Path

from briefbridge.config import BriefBridgeConfig
from briefbridge.ingest.manager import IngestManager
from briefbridge.models.enums import ImportMode
from briefbridge.models.handoff import HandoffPack
from briefbridge.render.json_export import render_json
from briefbridge.render.markdown import render_markdown
from briefbridge.render.plain_text import render_multi_mode, render_plain
from briefbridge.storage.sqlite import StorageBackend


class HandoffService:
    def __init__(
        self,
        config: BriefBridgeConfig | None = None,
        storage: StorageBackend | None = None,
    ) -> None:
        self.config = config or BriefBridgeConfig.load()
        self.storage = storage
        self._ingest = IngestManager(self.config)

    def generate_pack(self, session_id: str) -> HandoffPack:
        """Run the full ingestion + extraction pipeline and return a HandoffPack."""
        pack = self._ingest.build_handoff(session_id)

        # Cache to storage
        if self.storage:
            self.storage.upsert_handoff(pack)

        return pack

    def get_or_generate(self, session_id: str) -> HandoffPack:
        """Get cached handoff or generate a new one."""
        if self.storage:
            cached = self.storage.get_handoff(session_id)
            if cached:
                return cached
        return self.generate_pack(session_id)

    def export_pack(
        self,
        session_id: str,
        fmt: str = "json",
        output_dir: Path | None = None,
    ) -> Path:
        """Export handoff to a file and return the file path."""
        pack = self.get_or_generate(session_id)
        out_dir = output_dir or Path.cwd()

        # Sanitize session id for filename
        safe_id = session_id.replace(":", "-").replace("/", "-")

        if fmt == "json":
            content = render_json(pack)
            path = out_dir / f"handoff-{safe_id}.json"
        elif fmt == "md":
            content = render_markdown(pack)
            path = out_dir / f"handoff-{safe_id}.md"
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        path.write_text(content, encoding="utf-8")
        return path

    def use_pack(self, session_id: str, modes: list[ImportMode]) -> str:
        """Generate a context block for a specific import mode."""
        pack = self.get_or_generate(session_id)
        if len(modes) == 1:
            return render_plain(pack, modes[0])
        return render_multi_mode(pack, modes)

    def render_markdown(self, session_id: str) -> str:
        pack = self.get_or_generate(session_id)
        return render_markdown(pack)
