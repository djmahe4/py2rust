from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompilerError(Exception):
    message: str
    filename: str = "<unknown>"
    line: int = 0
    column: int = 0
    suggestion: Optional[str] = None
    source_lines: list = field(default_factory=list)

    def __str__(self) -> str:
        loc = f"{self.filename}:{self.line}:{self.column}"
        parts = [f"{self.__class__.__name__}: {loc}: {self.message}"]
        if self.source_lines and 0 < self.line <= len(self.source_lines):
            line_text = self.source_lines[self.line - 1]
            parts.append(f"  | {line_text}")
            if self.column > 0:
                parts.append(f"  | {' ' * (self.column - 1)}^")
        if self.suggestion:
            parts.append(f"  hint: {self.suggestion}")
        return "\n".join(parts)

    def __post_init__(self):
        super().__init__(str(self.message))


@dataclass
class ParseError(CompilerError):
    pass


@dataclass
class SemanticError(CompilerError):
    pass


@dataclass
class Py2RustTypeError(CompilerError):
    pass


@dataclass
class UnsupportedFeatureError(CompilerError):
    pass
