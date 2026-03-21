"""Comprehensive unit tests for core/diff_parser.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from codesentinel.core.diff_parser import LANGUAGE_MAP, DiffParser, _detect_language
from codesentinel.core.enums import FileStatus
from codesentinel.core.exceptions import DiffParseError

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "diffs"


@pytest.fixture()
def parser() -> DiffParser:
    return DiffParser()


# --------------------------------------------------------------------------- #
# LANGUAGE_MAP & language detection
# --------------------------------------------------------------------------- #


class TestLanguageMap:
    def test_common_extensions_present(self) -> None:
        assert LANGUAGE_MAP[".py"] == "python"
        assert LANGUAGE_MAP[".java"] == "java"
        assert LANGUAGE_MAP[".ts"] == "typescript"
        assert LANGUAGE_MAP[".tsx"] == "typescript"
        assert LANGUAGE_MAP[".js"] == "javascript"
        assert LANGUAGE_MAP[".go"] == "go"
        assert LANGUAGE_MAP[".rs"] == "rust"
        assert LANGUAGE_MAP[".rb"] == "ruby"

    def test_config_extensions(self) -> None:
        assert LANGUAGE_MAP[".yaml"] == "yaml"
        assert LANGUAGE_MAP[".yml"] == "yaml"
        assert LANGUAGE_MAP[".json"] == "json"
        assert LANGUAGE_MAP[".toml"] == "toml"

    def test_detect_language_from_path(self) -> None:
        assert _detect_language("src/main.py") == "python"
        assert _detect_language("src/App.tsx") == "typescript"
        assert _detect_language("build.gradle") == "groovy"

    def test_detect_language_unknown_extension(self) -> None:
        assert _detect_language("README") is None
        assert _detect_language("data.xyz") is None

    def test_detect_language_dockerfile(self) -> None:
        assert _detect_language("Dockerfile") == "dockerfile"
        assert _detect_language("Dockerfile.dev") == "dockerfile"

    def test_detect_language_makefile(self) -> None:
        assert _detect_language("Makefile") == "makefile"

    def test_detect_language_case_insensitive_extension(self) -> None:
        assert _detect_language("Component.JSX") == "javascript"


# --------------------------------------------------------------------------- #
# Empty / trivial input
# --------------------------------------------------------------------------- #


class TestEmptyInput:
    def test_empty_string(self, parser: DiffParser) -> None:
        result = parser.parse("")
        assert result.files == ()
        assert result.stats.files_changed == 0

    def test_whitespace_only(self, parser: DiffParser) -> None:
        result = parser.parse("   \n\n  ")
        assert result.files == ()

    def test_none_like_empty(self, parser: DiffParser) -> None:
        result = parser.parse("")
        assert result.stats.additions == 0
        assert result.stats.deletions == 0


# --------------------------------------------------------------------------- #
# Standard modified file
# --------------------------------------------------------------------------- #


class TestStandardModifiedFile:
    DIFF = """\
diff --git a/src/main.py b/src/main.py
index 1234567..89abcde 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,4 +1,5 @@
 import os
+import sys

 def main():
-    print("hello")
+    print("hello world")
"""

    def test_parses_one_file(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert len(result.files) == 1

    def test_file_path(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].path == "src/main.py"

    def test_file_status_modified(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].status == FileStatus.MODIFIED

    def test_language_detected(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].language == "python"

    def test_hunk_counts(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        hunk = result.files[0].hunks[0]
        assert hunk.old_start == 1
        assert hunk.old_count == 4
        assert hunk.new_start == 1
        assert hunk.new_count == 5

    def test_added_lines(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        hunk = result.files[0].hunks[0]
        assert "import sys" in hunk.added_lines
        assert '    print("hello world")' in hunk.added_lines

    def test_removed_lines(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        hunk = result.files[0].hunks[0]
        assert '    print("hello")' in hunk.removed_lines

    def test_context_lines(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        hunk = result.files[0].hunks[0]
        assert "import os" in hunk.context_lines

    def test_stats(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.stats.files_changed == 1
        assert result.stats.additions == 2
        assert result.stats.deletions == 1


# --------------------------------------------------------------------------- #
# New file (--- /dev/null)
# --------------------------------------------------------------------------- #


class TestNewFile:
    DIFF = (
        "diff --git a/src/new_module.py b/src/new_module.py\n"
        "new file mode 100644\n"
        "index 0000000..abc1234\n"
        "--- /dev/null\n"
        "+++ b/src/new_module.py\n"
        "@@ -0,0 +1,3 @@\n"
        '+"""A new module."""\n'
        "+\n"
        "+NEW_CONSTANT = 42\n"
    )

    def test_status_added(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].status == FileStatus.ADDED

    def test_old_path_none(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].old_path is None

    def test_path(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].path == "src/new_module.py"

    def test_added_line_count(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].added_line_count == 3


# --------------------------------------------------------------------------- #
# Deleted file (+++ /dev/null)
# --------------------------------------------------------------------------- #


class TestDeletedFile:
    DIFF = (
        "diff --git a/src/old_module.py b/src/old_module.py\n"
        "deleted file mode 100644\n"
        "index abc1234..0000000\n"
        "--- a/src/old_module.py\n"
        "+++ /dev/null\n"
        "@@ -1,5 +0,0 @@\n"
        '-"""An old module."""\n'
        "-\n"
        "-\n"
        "-def deprecated():\n"
        "-    pass\n"
    )

    def test_status_deleted(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].status == FileStatus.DELETED

    def test_path(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].path == "src/old_module.py"

    def test_removed_line_count(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].removed_line_count == 5


# --------------------------------------------------------------------------- #
# Renamed file
# --------------------------------------------------------------------------- #


class TestRenamedFile:
    DIFF = """\
diff --git a/old_name.py b/new_name.py
similarity index 95%
rename from old_name.py
rename to new_name.py
index 1234567..89abcde 100644
--- a/old_name.py
+++ b/new_name.py
@@ -1,3 +1,3 @@
-OLD_VAR = 1
+NEW_VAR = 1

 print("ok")
"""

    def test_status_renamed(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].status == FileStatus.RENAMED

    def test_path_is_new_name(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].path == "new_name.py"

    def test_old_path_is_old_name(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].old_path == "old_name.py"


# --------------------------------------------------------------------------- #
# Binary file
# --------------------------------------------------------------------------- #


class TestBinaryFile:
    DIFF = """\
diff --git a/assets/logo.png b/assets/logo.png
index 1234567..89abcde 100644
Binary files a/assets/logo.png and b/assets/logo.png differ
"""

    def test_is_binary(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].is_binary is True

    def test_no_hunks(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].hunks == ()

    def test_binary_language_none(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].language is None

    def test_stats_binary_count(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.stats.binary_files == 1


# --------------------------------------------------------------------------- #
# Mode change only
# --------------------------------------------------------------------------- #


class TestModeChange:
    DIFF = """\
diff --git a/run.sh b/run.sh
old mode 100644
new mode 100755
"""

    def test_parses_without_error(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert len(result.files) == 1

    def test_status_modified(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].status == FileStatus.MODIFIED

    def test_no_hunks(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].hunks == ()

    def test_language_shell(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].language == "shell"


# --------------------------------------------------------------------------- #
# Multiple files in a single diff
# --------------------------------------------------------------------------- #


class TestMultipleFiles:
    DIFF = """\
diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1,2 +1,3 @@
 x = 1
+y = 2
 z = 3
diff --git a/b.ts b/b.ts
index 3333333..4444444 100644
--- a/b.ts
+++ b/b.ts
@@ -1,3 +1,2 @@
 const a = 1;
-const b = 2;
 const c = 3;
"""

    def test_file_count(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert len(result.files) == 2

    def test_file_languages(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].language == "python"
        assert result.files[1].language == "typescript"

    def test_aggregate_stats(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.stats.files_changed == 2
        assert result.stats.additions == 1
        assert result.stats.deletions == 1


# --------------------------------------------------------------------------- #
# Multiple hunks in a single file
# --------------------------------------------------------------------------- #


class TestMultipleHunks:
    DIFF = """\
diff --git a/src/utils.py b/src/utils.py
index aaa1111..bbb2222 100644
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,3 +1,4 @@
 import os
+import sys

 def foo():
@@ -10,3 +11,4 @@

 def bar():
+    print("bar")
     pass
"""

    def test_two_hunks(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert len(result.files[0].hunks) == 2

    def test_first_hunk_position(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        h = result.files[0].hunks[0]
        assert h.old_start == 1
        assert h.new_start == 1

    def test_second_hunk_position(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        h = result.files[0].hunks[1]
        assert h.old_start == 10
        assert h.new_start == 11


# --------------------------------------------------------------------------- #
# Hunk with single line (no count in header)
# --------------------------------------------------------------------------- #


class TestSingleLineHunk:
    DIFF = """\
diff --git a/one.py b/one.py
index 1234567..89abcde 100644
--- a/one.py
+++ b/one.py
@@ -1 +1 @@
-old_value = 1
+new_value = 2
"""

    def test_count_defaults_to_one(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        hunk = result.files[0].hunks[0]
        assert hunk.old_count == 1
        assert hunk.new_count == 1


# --------------------------------------------------------------------------- #
# No newline at end of file marker
# --------------------------------------------------------------------------- #


class TestNoNewlineMarker:
    DIFF = """\
diff --git a/file.txt b/file.txt
index 1234567..89abcde 100644
--- a/file.txt
+++ b/file.txt
@@ -1,2 +1,2 @@
-old line
+new line
\\ No newline at end of file
"""

    def test_no_newline_skipped(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        hunk = result.files[0].hunks[0]
        assert len(hunk.added_lines) == 1
        assert len(hunk.removed_lines) == 1
        assert "No newline" not in hunk.added_lines[0]


# --------------------------------------------------------------------------- #
# parse_file method
# --------------------------------------------------------------------------- #


class TestParseFile:
    def test_parse_fixture_java(self, parser: DiffParser) -> None:
        result = parser.parse_file(str(FIXTURES_DIR / "java_clean_arch_violation.diff"))
        assert len(result.files) == 2
        assert result.files[0].language == "java"
        assert result.files[0].status == FileStatus.ADDED

    def test_parse_fixture_python(self, parser: DiffParser) -> None:
        result = parser.parse_file(str(FIXTURES_DIR / "python_django_violation.diff"))
        assert len(result.files) == 2
        assert result.files[0].language == "python"

    def test_parse_fixture_typescript(self, parser: DiffParser) -> None:
        result = parser.parse_file(str(FIXTURES_DIR / "typescript_react_violation.diff"))
        assert len(result.files) == 2
        tsx_file = result.files[0]
        ts_file = result.files[1]
        assert tsx_file.language == "typescript"
        assert ts_file.language == "typescript"

    def test_parse_fixture_clean(self, parser: DiffParser) -> None:
        result = parser.parse_file(str(FIXTURES_DIR / "clean_pr_no_issues.diff"))
        assert len(result.files) == 2
        assert result.stats.additions > 0

    def test_file_not_found(self, parser: DiffParser) -> None:
        with pytest.raises(DiffParseError, match="not found"):
            parser.parse_file("/nonexistent/path.diff")

    def test_file_not_found_message(self, parser: DiffParser) -> None:
        with pytest.raises(DiffParseError):
            parser.parse_file("/tmp/no_such_file_12345.diff")


# --------------------------------------------------------------------------- #
# Edge cases: empty file addition/deletion
# --------------------------------------------------------------------------- #


class TestEmptyFileDiff:
    DIFF = """\
diff --git a/empty.py b/empty.py
new file mode 100644
index 0000000..e69de29
"""

    def test_empty_new_file(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert len(result.files) == 1
        assert result.files[0].status == FileStatus.ADDED
        assert result.files[0].hunks == ()


# --------------------------------------------------------------------------- #
# Rename without content changes (100% similarity)
# --------------------------------------------------------------------------- #


class TestRenameNoChanges:
    DIFF = """\
diff --git a/old/path.py b/new/path.py
similarity index 100%
rename from old/path.py
rename to new/path.py
"""

    def test_pure_rename(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        f = result.files[0]
        assert f.status == FileStatus.RENAMED
        assert f.path == "new/path.py"
        assert f.old_path == "old/path.py"
        assert f.hunks == ()


# --------------------------------------------------------------------------- #
# DiffHunk content field
# --------------------------------------------------------------------------- #


class TestHunkContent:
    DIFF = """\
diff --git a/f.py b/f.py
index 1234567..89abcde 100644
--- a/f.py
+++ b/f.py
@@ -1,2 +1,2 @@
-old
+new
 same
"""

    def test_content_is_raw_body(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        content = result.files[0].hunks[0].content
        assert "-old" in content
        assert "+new" in content
        assert " same" in content


# --------------------------------------------------------------------------- #
# FileDiff properties
# --------------------------------------------------------------------------- #


class TestFileDiffProperties:
    DIFF = """\
diff --git a/count.py b/count.py
index 1234567..89abcde 100644
--- a/count.py
+++ b/count.py
@@ -1,3 +1,5 @@
 a = 1
-b = 2
+b = 20
+c = 30
+d = 40
 e = 5
"""

    def test_added_line_count(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].added_line_count == 3

    def test_removed_line_count(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].removed_line_count == 1


# --------------------------------------------------------------------------- #
# Mixed: binary + text files in one diff
# --------------------------------------------------------------------------- #


class TestMixedBinaryAndText:
    DIFF = """\
diff --git a/icon.png b/icon.png
index 1234567..89abcde 100644
Binary files a/icon.png and b/icon.png differ
diff --git a/readme.md b/readme.md
index aaa1111..bbb2222 100644
--- a/readme.md
+++ b/readme.md
@@ -1,2 +1,3 @@
 # Project
+New line added.
 End.
"""

    def test_file_count(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert len(result.files) == 2

    def test_binary_and_text(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].is_binary is True
        assert result.files[1].is_binary is False

    def test_binary_stats(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.stats.binary_files == 1
        assert result.stats.additions == 1


# --------------------------------------------------------------------------- #
# New file with new file mode but standard --- / +++ headers
# --------------------------------------------------------------------------- #


class TestNewFileWithHeaders:
    DIFF = """\
diff --git a/config.yaml b/config.yaml
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/config.yaml
@@ -0,0 +1,2 @@
+key: value
+other: data
"""

    def test_new_yaml_file(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        f = result.files[0]
        assert f.status == FileStatus.ADDED
        assert f.language == "yaml"
        assert f.added_line_count == 2


# --------------------------------------------------------------------------- #
# Deleted file with explicit "deleted file mode" header
# --------------------------------------------------------------------------- #


class TestDeletedFileMode:
    """Cover line 383-384: deleted file detected via `deleted file mode` header."""

    DIFF = """\
diff --git a/src/removed.py b/src/removed.py
deleted file mode 100644
index abc1234..0000000
--- a/src/removed.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old_func():
-    pass
"""

    def test_status_deleted_via_mode(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].status == FileStatus.DELETED

    def test_path_from_old(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].path == "src/removed.py"


# --------------------------------------------------------------------------- #
# parse_file with unreadable file (OSError)
# --------------------------------------------------------------------------- #


class TestParseFileOSError:
    def test_directory_as_path_raises(self, parser: DiffParser, tmp_path: Path) -> None:
        """Attempting to read a directory should raise DiffParseError."""
        with pytest.raises(DiffParseError):
            parser.parse_file(str(tmp_path))


# --------------------------------------------------------------------------- #
# Deleted file with only `deleted file mode` and no --- /dev/null
# --------------------------------------------------------------------------- #


class TestDeletedFileModeNoDevNull:
    """Cover line 383-384: deleted file via is_deleted flag only."""

    DIFF = """\
diff --git a/src/stale.py b/src/stale.py
deleted file mode 100644
index abc1234..0000000
"""

    def test_deleted_via_flag_only(self, parser: DiffParser) -> None:
        result = parser.parse(self.DIFF)
        assert result.files[0].status == FileStatus.DELETED
        assert result.files[0].path == "src/stale.py"
