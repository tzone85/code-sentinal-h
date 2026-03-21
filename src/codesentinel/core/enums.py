"""Core enumerations for CodeSentinel."""

from enum import Enum


class FileStatus(str, Enum):
    """Status of a file in a diff."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"


class FileType(str, Enum):
    """Classification of a file's purpose."""

    SOURCE = "source"
    TEST = "test"
    CONFIG = "config"
    MIGRATION = "migration"
    DOCS = "docs"
    CI = "ci"


class Severity(str, Enum):
    """Finding severity level, ordered from most to least severe."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def weight(self) -> int:
        """Numeric weight for severity comparison (higher = more severe)."""
        weights = {
            Severity.CRITICAL: 5,
            Severity.HIGH: 4,
            Severity.MEDIUM: 3,
            Severity.LOW: 2,
            Severity.INFO: 1,
        }
        return weights[self]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.weight >= other.weight

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.weight > other.weight

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.weight <= other.weight

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.weight < other.weight
