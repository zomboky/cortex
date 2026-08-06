from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Note:
    title: str
    source_path: str
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    body: str = ""
    candidate_topics: list[str] = field(default_factory=list)
    created: str = ""
