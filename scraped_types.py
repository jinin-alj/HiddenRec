from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScrapedResult:
    platform: str
    text: str
    url: str
