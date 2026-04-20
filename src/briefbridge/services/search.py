"""FTS-based local search/ask service."""

from __future__ import annotations

from briefbridge.config import BriefBridgeConfig
from briefbridge.storage.sqlite import SearchResult, StorageBackend


class SearchService:
    def __init__(
        self,
        config: BriefBridgeConfig | None = None,
        storage: StorageBackend | None = None,
    ) -> None:
        self.config = config or BriefBridgeConfig.load()
        self.storage = storage

    def ask(self, session_id: str, question: str) -> str:
        """Answer a question about a session using FTS search + pack data."""
        if not self.storage:
            return self._ask_without_storage(session_id, question)

        # First try to get the handoff pack for targeted search
        pack = self.storage.get_handoff(session_id)
        if pack:
            return self._search_pack(pack, question)

        # Fall back to FTS
        results = self.storage.search(question)
        if results:
            lines = []
            for r in results[:5]:
                lines.append(f"[{r.session_id}] {r.title}")
                lines.append(f"  {r.snippet}")
            return "\n".join(lines)

        return "No relevant information found. Try running `bb pack` first."

    def _ask_without_storage(self, session_id: str, question: str) -> str:
        """Generate a pack on-the-fly and search it."""
        from briefbridge.ingest.manager import IngestManager

        mgr = IngestManager(self.config)
        try:
            pack = mgr.build_handoff(session_id)
        except FileNotFoundError:
            return f"Session not found: {session_id}"
        return self._search_pack(pack, question)

    @staticmethod
    def _search_pack(pack, question: str) -> str:
        """Simple keyword search across pack fields."""
        from briefbridge.models.handoff import HandoffPack

        assert isinstance(pack, HandoffPack)
        keywords = question.lower().split()
        results: list[str] = []

        # Search objective
        if pack.objective and any(kw in pack.objective.lower() for kw in keywords):
            results.append(f"Objective: {pack.objective}")

        # Search hypothesis
        if pack.main_hypothesis and any(
            kw in pack.main_hypothesis.lower() for kw in keywords
        ):
            results.append(f"Hypothesis: {pack.main_hypothesis}")

        # Search errors
        for err in pack.errors_found:
            if any(kw in err.summary.lower() for kw in keywords):
                results.append(f"Error: {err.summary}")
            elif any(kw in err.raw_excerpt.lower() for kw in keywords):
                results.append(f"Error: {err.summary}")

        # Search commands
        for cmd in pack.important_commands:
            if any(kw in cmd.command.lower() for kw in keywords):
                results.append(f"Command: {cmd.command} — {cmd.summary}")

        # Search decisions
        for d in pack.decisions_made:
            if any(kw in d.text.lower() for kw in keywords):
                results.append(f"Decision: {d.text}")

        # Search pending
        for p in pack.pending_items:
            if any(kw in p.text.lower() for kw in keywords):
                results.append(f"Pending: {p.text}")

        # Search files
        for f in pack.relevant_files:
            if any(kw in f.path.lower() for kw in keywords):
                results.append(f"File: {f.path} ({f.role})")

        if results:
            return "\n".join(results)

        return "No matches found for your question in this session."
