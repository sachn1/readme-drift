"""Shared data models for readme-check."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ChangeType(Enum):
    """Types of changes that can occur to a public symbol."""

    ADDED = "added"
    REMOVED = "removed"
    SIGNATURE_CHANGED = "signature_changed"
    RENAMED = "renamed"


@dataclass
class GitDiffResult:
    """Files that changed in a git diff, plus their old and new source contents."""

    changed_py_files: list[Path]
    readme_changed: bool
    old_file_contents: dict[str, str] = field(default_factory=dict)
    new_file_contents: dict[str, str] = field(default_factory=dict)


@dataclass
class PublicAPI:
    """Snapshot of a module's public API surface extracted from its AST."""

    functions: dict[str, str] = field(default_factory=dict)  # name → signature
    classes: dict[str, set[str]] = field(
        default_factory=dict
    )  # name → set of method signatures
    methods: dict[str, str] = field(default_factory=dict)  # "Class.method" → signature


@dataclass
class SymbolChange:
    """A public symbol (function, method, or class) that changed between two file versions."""

    name: str
    change_type: ChangeType
    old_signature: str | None = None
    new_signature: str | None = None
    file: str = ""

    def __str__(self) -> str:
        match self.change_type:
            case ChangeType.ADDED:
                return f"`{self.name}` was added"
            case ChangeType.REMOVED:
                return f"`{self.name}` was removed"
            case ChangeType.SIGNATURE_CHANGED:
                return (
                    f"`{self.name}` signature changed: "
                    f"{self.old_signature} → {self.new_signature}"
                )
            case ChangeType.RENAMED:
                return f"`{self.old_signature}` was renamed to `{self.name}`"


@dataclass
class ReadmeMatch:
    """A line in the README where a changed symbol name was found."""

    symbol: str
    line_number: int
    line_text: str
    matched_text: str
    readme_path: Path


@dataclass
class StalenessFinding:
    """A symbol change that is referenced in the README, indicating potential staleness."""

    change: SymbolChange
    readme_matches: list[ReadmeMatch]

    @property
    def symbol(self) -> str:
        return self.change.name


@dataclass
class CheckResult:
    """The overall result of a readme-check run."""

    findings: list[StalenessFinding] = field(default_factory=list)
    readme_was_updated: bool = False
    readme_paths: list[Path] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def passed(self) -> bool:
        return self.skipped or self.readme_was_updated or len(self.findings) == 0

    @property
    def failed(self) -> bool:
        return not self.passed
