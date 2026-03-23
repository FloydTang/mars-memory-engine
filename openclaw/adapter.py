"""
OpenClaw adapter for a Markdown-first memory engine.

This layer treats workspace Markdown files as the source of truth and
uses LanceDB only as a derived index for retrieval and ranking.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.lancedb_store import (
    LanceDBMemoryStore,
    derive_fact_key,
    get_embedder,
    slugify_section,
)
from protocols.memory_gateway import MemoryGateway

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


@dataclass
class WorkspaceContext:
    workspace_path: str
    agent_id: str
    guild_id: str
    session_scope: str = "private"


@dataclass
class MemoryRef:
    memory_id: str
    source_file: str
    source_section: str
    block_id: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "memory_id": self.memory_id,
            "source_file": self.source_file,
            "source_section": self.source_section,
            "block_id": self.block_id,
        }


@dataclass
class MarkdownMemoryEntry:
    content: str
    title: str
    topic: str = "general"
    category: Optional[str] = None
    importance: float = 0.5
    confidence: float = 0.7
    scope: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    target_file: Optional[str] = None


class OpenClawMemoryAdapter:
    """Markdown-first adapter that bridges OpenClaw workspaces and Mars retrieval."""

    def __init__(
        self,
        workspace_path: str,
        gateway: Optional[MemoryGateway] = None,
        db_path: Optional[str] = None,
        embedder=None,
    ):
        self.workspace_path = Path(workspace_path).expanduser()
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or str(self.workspace_path / ".mars-memory-engine" / "lancedb")
        self.embedder = embedder or get_embedder()
        self.gateway = gateway or MemoryGateway(
            store=LanceDBMemoryStore(self.db_path),
            embedder=self.embedder,
        )
        self._lock_path = self.workspace_path / ".mars-memory-engine" / "index.lock"
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)

    def ingest_markdown_memory(
        self,
        entry: MarkdownMemoryEntry,
        workspace_context: WorkspaceContext,
    ) -> Dict:
        target_path = self._resolve_target_file(entry, workspace_context)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        block_id = self._build_block_id(entry.title, entry.content)
        section_title = entry.title.strip() or f"{entry.topic.title()} Memory"
        metadata = dict(entry.metadata)
        metadata.setdefault("agent_id", workspace_context.agent_id)
        metadata.setdefault("guild_id", workspace_context.guild_id)
        metadata.setdefault("scope", entry.scope or workspace_context.session_scope)
        markdown_block = self._format_markdown_block(section_title, block_id, entry, metadata)

        with self._workspace_lock():
            with target_path.open("a", encoding="utf-8") as handle:
                handle.write(markdown_block)

        metadata.setdefault("stable_fact_key", derive_fact_key(
            category=entry.category or "pattern",
            topic=entry.topic,
            content=entry.content,
            source_section=section_title,
            metadata=entry.metadata,
        ))

        return asyncio.run(
            self.gateway.write_memory(
                content=entry.content,
                agent_id=workspace_context.agent_id,
                guild_id=workspace_context.guild_id,
                category=entry.category,
                scope=entry.scope or workspace_context.session_scope,
                topic=entry.topic,
                confidence=entry.confidence,
                importance=entry.importance,
                metadata=metadata,
                source="openclaw_markdown",
                source_file=str(target_path),
                source_section=section_title,
                source_type=self._infer_source_type(target_path),
                fact_key_override=metadata.get("stable_fact_key") or None,
            )
        )

    def search_memory(
        self,
        query: str,
        workspace_context: WorkspaceContext,
        include_history: bool = False,
        limit: int = 5,
    ) -> List[Dict]:
        results = self.gateway.search(
            query=query,
            agent_id=workspace_context.agent_id,
            guild_id=workspace_context.guild_id,
            limit=limit,
            include_history=include_history,
        )

        shaped = []
        for item in results:
            source_file = item.get("source_file") or ""
            source_section = item.get("source_section") or item.get("topic") or "memory"
            block_id = item.get("entry_hash") or slugify_section(source_section)
            shaped.append({
                "memory_ref": MemoryRef(
                    memory_id=item["id"],
                    source_file=source_file,
                    source_section=source_section,
                    block_id=block_id,
                ).to_dict(),
                "source_file": source_file,
                "source_section": source_section,
                "category": item.get("category", "pattern"),
                "tier": item.get("tier", "peripheral"),
                "summary_l1": item.get("summary_l1", ""),
                "raw_excerpt": item.get("raw_excerpt", ""),
                "score": item.get("final_score", item.get("rrf_score", 0.0)),
                "is_history": item.get("is_history", False),
            })
        return shaped

    def promote_memory(
        self,
        memory_ref: Dict[str, str],
        target_doc: str,
    ) -> Path:
        source_file = Path(memory_ref["source_file"])
        source_section = memory_ref["source_section"]
        content = self._extract_section(source_file, source_section)
        if not content:
            raise ValueError(f"Unable to find section '{source_section}' in {source_file}")

        target_path = self.workspace_path / target_doc
        target_path.parent.mkdir(parents=True, exist_ok=True)
        promoted_block = (
            f"\n## {source_section}\n\n"
            f"{content.strip()}\n\n"
            f"*Promoted from: {source_file.relative_to(self.workspace_path)}*\n"
        )
        with self._workspace_lock():
            with target_path.open("a", encoding="utf-8") as handle:
                handle.write(promoted_block)
        return target_path

    def rebuild_index(self, workspace_path: Optional[str] = None) -> Dict[str, int]:
        workspace = Path(workspace_path or self.workspace_path).expanduser()
        db_dir = Path(self.db_path)
        if db_dir.exists():
            shutil.rmtree(db_dir)

        self.gateway = MemoryGateway(
            store=LanceDBMemoryStore(self.db_path),
            embedder=self.embedder,
        )
        parsed = self._scan_workspace(workspace)
        indexed = 0
        for entry in parsed:
            asyncio.run(
                self.gateway.write_memory(
                    content=entry["content"],
                    agent_id=entry["agent_id"],
                    guild_id=entry["guild_id"],
                    category=entry["category"],
                    scope=entry["scope"],
                    topic=entry["topic"],
                    confidence=entry["confidence"],
                    importance=entry["importance"],
                    metadata=entry["metadata"],
                    source="openclaw_markdown",
                    source_file=entry["source_file"],
                    source_section=entry["source_section"],
                    source_type=entry["source_type"],
                    fact_key_override=entry["fact_key"],
                )
            )
            indexed += 1
        return {"indexed_entries": indexed, "scanned_files": len(self._memory_files(workspace))}

    def _scan_workspace(self, workspace: Path) -> List[Dict]:
        entries: List[Dict] = []
        for file_path in self._memory_files(workspace):
            content = file_path.read_text(encoding="utf-8")
            for section in self._parse_sections(content):
                section_content = section["body"].strip()
                if len(section_content) < 12:
                    continue
                category = section["metadata"].get("category")
                topic = section["metadata"].get("topic") or self._topic_from_path(file_path)
                entries.append({
                    "content": section_content,
                    "agent_id": section["metadata"].get("agent_id", "openclaw"),
                    "guild_id": section["metadata"].get("guild_id", "workspace"),
                    "scope": section["metadata"].get("scope", "shared"),
                    "category": category,
                    "topic": topic,
                    "confidence": float(section["metadata"].get("confidence", 0.7)),
                    "importance": float(section["metadata"].get("importance", 0.5)),
                    "metadata": section["metadata"],
                    "source_file": str(file_path),
                    "source_section": section["title"],
                    "source_type": self._infer_source_type(file_path),
                    "fact_key": derive_fact_key(
                        category=category or "pattern",
                        topic=topic,
                        content=section_content,
                        source_section=section["title"],
                        metadata=section["metadata"],
                    ),
                })
        return entries

    def _memory_files(self, workspace: Path) -> List[Path]:
        files: List[Path] = []
        root_memory = workspace / "MEMORY.md"
        if root_memory.exists():
            files.append(root_memory)

        memory_dir = workspace / "memory"
        if memory_dir.exists():
            files.extend(sorted(memory_dir.glob("*.md")))
            topics_dir = memory_dir / "topics"
            if topics_dir.exists():
                files.extend(sorted(topics_dir.glob("*.md")))
        return files

    def _parse_sections(self, content: str) -> List[Dict]:
        matches = list(re.finditer(r"^##\s+(.+)$", content, flags=re.MULTILINE))
        sections: List[Dict] = []
        for idx, match in enumerate(matches):
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
            block = content[start:end].strip()
            if not block:
                continue
            metadata = {}
            for key in ("category", "topic", "agent_id", "guild_id", "scope", "confidence", "importance", "stable_fact_key"):
                found = re.search(rf"\*{key}:\s*(.+?)\*", block)
                if found:
                    metadata[key] = found.group(1).strip()
            body = re.sub(r"^\*.+?:.+?\*\n?", "", block, flags=re.MULTILINE).strip()
            sections.append({
                "title": match.group(1).strip(),
                "body": body,
                "metadata": metadata,
            })
        return sections

    def _resolve_target_file(self, entry: MarkdownMemoryEntry, workspace_context: WorkspaceContext) -> Path:
        if entry.target_file:
            return self.workspace_path / entry.target_file
        if entry.topic == "general":
            return self.workspace_path / "MEMORY.md"
        return self.workspace_path / "memory" / "topics" / f"{slugify_section(entry.topic)}.md"

    def _format_markdown_block(
        self,
        title: str,
        block_id: str,
        entry: MarkdownMemoryEntry,
        metadata: Dict,
    ) -> str:
        metadata_lines = [
            f"*category: {entry.category or 'pattern'}*",
            f"*topic: {entry.topic}*",
            f"*confidence: {entry.confidence:.2f}*",
            f"*importance: {entry.importance:.2f}*",
            f"*agent_id: {metadata.get('agent_id', 'openclaw')}*",
            f"*guild_id: {metadata.get('guild_id', 'workspace')}*",
            f"*scope: {metadata.get('scope', entry.scope or 'private')}*",
            f"*block_id: {block_id}*",
        ]
        if metadata.get("stable_fact_key"):
            metadata_lines.append(f"*stable_fact_key: {metadata['stable_fact_key']}*")
        return (
            f"\n## {title}\n\n"
            + "\n".join(metadata_lines)
            + f"\n\n{entry.content.strip()}\n"
        )

    def _build_block_id(self, title: str, content: str) -> str:
        payload = f"{title}|{content[:80]}"
        return hashlib.md5(payload.encode()).hexdigest()[:12]

    def _infer_source_type(self, file_path: Path) -> str:
        rel = file_path.relative_to(self.workspace_path)
        if rel.name == "MEMORY.md":
            return "memory_index"
        if "topics" in rel.parts:
            return "topic"
        return "daily"

    def _topic_from_path(self, file_path: Path) -> str:
        if file_path.name == "MEMORY.md":
            return "general"
        if file_path.parent.name == "topics":
            return file_path.stem
        return "daily"

    def _extract_section(self, file_path: Path, section_title: str) -> str:
        content = file_path.read_text(encoding="utf-8")
        for section in self._parse_sections(content):
            if section["title"] == section_title:
                return section["body"]
        return ""

    def _workspace_lock(self):
        if fcntl is None:
            return _NullLock()
        return _FileLock(self._lock_path)


class _FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
        return False


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
