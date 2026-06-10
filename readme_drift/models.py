"""Shared data models for readme-drift."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ChangeType(Enum):
    """Types of changes that can occur to a public symbol."""

    ADDED = "added"
    REMOVED = "removed"
    SIGNATURE_CHANGED = "signature_changed"


@dataclass
class GitDiffResult:
    """Files that changed in a git diff."""

    changed_py_files: list[Path]
    changed_config_files: list[Path] = field(default_factory=list)


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
    # Rename tracking: the original name before a rename (distinct from old_signature,
    # which stores the old signature string for SIGNATURE_CHANGED).
    old_name: str | None = None
    # Full dot-notation key paths that contained this symbol (config changes only).
    # e.g. the leaf "build" from "scripts.build" → key_paths=["scripts.build"].
    key_paths: list[str] = field(default_factory=list)

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
        """Name of the changed symbol."""
        return self.change.name


@dataclass
class DriftCheckResult:
    """The overall result of a readme-drift run."""

    findings: list[StalenessFinding] = field(default_factory=list)
    readme_paths: list[Path] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    # Populated when --verbose is active; each entry is a human-readable line
    # describing one symbol change and its fate (flagged / not in README /
    # suppressed / denied / force-flagged via allowlist).
    verbose_log: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if no findings or the run was skipped."""
        return self.skipped or len(self.findings) == 0

    @property
    def failed(self) -> bool:
        """True if there are unresolved staleness findings."""
        return not self.passed
