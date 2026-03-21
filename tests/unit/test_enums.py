"""Unit tests for core/enums.py — FileStatus, FileType, Severity.

Focuses on Severity comparison operators and weight property
which are the primary uncovered lines.
"""

from __future__ import annotations

from codesentinel.core.enums import FileStatus, FileType, Severity

# --------------------------------------------------------------------------- #
# Severity weight property
# --------------------------------------------------------------------------- #


class TestSeverityWeight:
    def test_critical_is_highest(self) -> None:
        assert Severity.CRITICAL.weight == 5

    def test_info_is_lowest(self) -> None:
        assert Severity.INFO.weight == 1

    def test_weight_ordering(self) -> None:
        weights = [s.weight for s in [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]]
        assert weights == [1, 2, 3, 4, 5]


# --------------------------------------------------------------------------- #
# Severity __ge__ (>=)
# --------------------------------------------------------------------------- #


class TestSeverityGe:
    def test_critical_ge_all(self) -> None:
        for s in Severity:
            assert s <= Severity.CRITICAL

    def test_info_ge_self(self) -> None:
        assert Severity.INFO >= Severity.INFO

    def test_info_not_ge_low(self) -> None:
        assert not (Severity.INFO >= Severity.LOW)

    def test_not_implemented_for_non_severity(self) -> None:
        result = Severity.HIGH.__ge__("not a severity")
        assert result is NotImplemented


# --------------------------------------------------------------------------- #
# Severity __gt__ (>)
# --------------------------------------------------------------------------- #


class TestSeverityGt:
    def test_critical_gt_high(self) -> None:
        assert Severity.CRITICAL > Severity.HIGH

    def test_high_not_gt_critical(self) -> None:
        assert not (Severity.HIGH > Severity.CRITICAL)

    def test_equal_not_gt(self) -> None:
        assert not (Severity.MEDIUM > Severity.MEDIUM)

    def test_not_implemented_for_non_severity(self) -> None:
        result = Severity.HIGH.__gt__(42)
        assert result is NotImplemented


# --------------------------------------------------------------------------- #
# Severity __le__ (<=)
# --------------------------------------------------------------------------- #


class TestSeverityLe:
    def test_info_le_all(self) -> None:
        for s in Severity:
            assert s >= Severity.INFO

    def test_critical_le_self(self) -> None:
        assert Severity.CRITICAL <= Severity.CRITICAL

    def test_critical_not_le_high(self) -> None:
        assert not (Severity.CRITICAL <= Severity.HIGH)

    def test_not_implemented_for_non_severity(self) -> None:
        result = Severity.LOW.__le__("string")
        assert result is NotImplemented


# --------------------------------------------------------------------------- #
# Severity __lt__ (<)
# --------------------------------------------------------------------------- #


class TestSeverityLt:
    def test_low_lt_medium(self) -> None:
        assert Severity.LOW < Severity.MEDIUM

    def test_critical_not_lt_any(self) -> None:
        for s in Severity:
            assert not (s > Severity.CRITICAL)

    def test_equal_not_lt(self) -> None:
        assert not (Severity.HIGH < Severity.HIGH)

    def test_not_implemented_for_non_severity(self) -> None:
        result = Severity.MEDIUM.__lt__(3.14)
        assert result is NotImplemented


# --------------------------------------------------------------------------- #
# Severity is a str enum
# --------------------------------------------------------------------------- #


class TestSeverityStr:
    def test_string_value(self) -> None:
        assert Severity.CRITICAL.value == "critical"
        assert str(Severity.CRITICAL) == "Severity.CRITICAL" or "critical" in str(Severity.CRITICAL)

    def test_membership(self) -> None:
        assert Severity("critical") == Severity.CRITICAL
        assert Severity("info") == Severity.INFO


# --------------------------------------------------------------------------- #
# FileStatus and FileType str enum basics
# --------------------------------------------------------------------------- #


class TestFileStatus:
    def test_values(self) -> None:
        assert FileStatus.ADDED.value == "added"
        assert FileStatus.MODIFIED.value == "modified"
        assert FileStatus.DELETED.value == "deleted"
        assert FileStatus.RENAMED.value == "renamed"
        assert FileStatus.COPIED.value == "copied"


class TestFileType:
    def test_values(self) -> None:
        assert FileType.SOURCE.value == "source"
        assert FileType.TEST.value == "test"
        assert FileType.CONFIG.value == "config"
        assert FileType.MIGRATION.value == "migration"
        assert FileType.DOCS.value == "docs"
        assert FileType.CI.value == "ci"
