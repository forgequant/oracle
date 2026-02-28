"""Shared signal protocols for oracle skills."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SignalOutput:
    signal: str
    confidence: int
    reasoning: str
    data: dict[str, Any] = field(default_factory=dict)
    analytics: dict[str, Any] = field(default_factory=dict)
    schema: str = "signal/v1"

    def emit(self) -> None:
        print(json.dumps(asdict(self), ensure_ascii=False))

    def summary(self, text: str) -> None:
        print(text, file=sys.stderr)


@dataclass
class ErrorOutput:
    error: str
    details: str = ""
    schema: str = "error/v1"

    def emit(self, exit: bool = True) -> None:
        print(json.dumps(asdict(self), ensure_ascii=False))
        if exit:
            sys.exit(1)
