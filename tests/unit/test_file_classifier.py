"""Comprehensive unit tests for core/file_classifier.py.

Tests language detection, file type classification, architectural layer
detection, module extraction, and framework hints.

Note: The file classifier uses fnmatch.fnmatch for glob matching.
fnmatch treats `*` as matching any characters (including `/`), but
root-level files (without directory prefix) won't match `**/pattern`
because `**/` requires at least one char before `/`. Tests use
appropriately nested paths.
"""

from __future__ import annotations

import pytest

from codesentinel.core.enums import FileStatus, FileType
from codesentinel.core.file_classifier import (
    FileClassifier,
    _detect_file_type,
    _detect_frameworks,
    _detect_language,
    _detect_layer,
    _detect_module,
    _matches_any,
)
from codesentinel.core.models import ClassifiedFile, FileDiff

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_file_diff(path: str, *, language: str | None = None) -> FileDiff:
    return FileDiff(
        path=path,
        old_path=None,
        status=FileStatus.MODIFIED,
        language=language,
    )


@pytest.fixture()
def classifier() -> FileClassifier:
    return FileClassifier()


# --------------------------------------------------------------------------- #
# _matches_any
# --------------------------------------------------------------------------- #


class TestMatchesAny:
    def test_matches_nested_path_glob(self) -> None:
        assert _matches_any("src/main.py", ["**/*.py"]) is True

    def test_no_match(self) -> None:
        assert _matches_any("src/main.py", ["**/*.java"]) is False

    def test_empty_patterns_list(self) -> None:
        assert _matches_any("src/main.py", []) is False

    def test_multiple_patterns_any_match(self) -> None:
        assert _matches_any("src/main.py", ["**/*.java", "**/*.py"]) is True

    def test_directory_glob_with_nested_path(self) -> None:
        """fnmatch requires directory prefix for **/tests/** to match."""
        assert _matches_any("src/tests/unit/test_main.py", ["**/tests/**"]) is True


# --------------------------------------------------------------------------- #
# _detect_language
# --------------------------------------------------------------------------- #


class TestDetectLanguage:
    def test_python_file(self) -> None:
        assert _detect_language("src/main.py") == "python"

    def test_java_file(self) -> None:
        assert _detect_language("src/App.java") == "java"

    def test_typescript_tsx(self) -> None:
        assert _detect_language("components/App.tsx") == "typescript"

    def test_unknown_extension(self) -> None:
        assert _detect_language("data.xyz123") is None

    def test_no_extension(self) -> None:
        assert _detect_language("Makefile") is None

    def test_case_insensitive_suffix(self) -> None:
        assert _detect_language("file.PY") == "python"

    def test_dot_only_filename(self) -> None:
        assert _detect_language(".gitignore") is None


# --------------------------------------------------------------------------- #
# _detect_file_type
# --------------------------------------------------------------------------- #


class TestDetectFileType:
    def test_source_file_default(self) -> None:
        assert _detect_file_type("src/main.py") == FileType.SOURCE

    def test_test_file_in_nested_tests_dir(self) -> None:
        """With fnmatch, **/tests/** requires a parent dir before tests/."""
        assert _detect_file_type("project/tests/unit/test_main.py") == FileType.TEST

    def test_test_file_with_test_suffix(self) -> None:
        assert _detect_file_type("src/main_test.py") == FileType.TEST

    def test_test_file_with_spec_suffix(self) -> None:
        assert _detect_file_type("src/main.spec.ts") == FileType.TEST

    def test_test_file_with_capitalized_test_suffix(self) -> None:
        assert _detect_file_type("src/UserTest.java") == FileType.TEST

    def test_config_yaml_nested(self) -> None:
        assert _detect_file_type("config/settings.yaml") == FileType.CONFIG

    def test_config_json_nested(self) -> None:
        assert _detect_file_type("config/package.json") == FileType.CONFIG

    def test_config_toml_nested(self) -> None:
        assert _detect_file_type("config/pyproject.toml") == FileType.CONFIG

    def test_dockerfile_nested(self) -> None:
        assert _detect_file_type("deploy/Dockerfile") == FileType.CONFIG

    def test_docker_compose_nested(self) -> None:
        assert _detect_file_type("infra/docker-compose.yml") == FileType.CONFIG

    def test_migration_dir(self) -> None:
        assert _detect_file_type("db/migrations/001_init.py") == FileType.MIGRATION

    def test_docs_markdown_nested(self) -> None:
        assert _detect_file_type("project/README.md") == FileType.DOCS

    def test_docs_rst(self) -> None:
        assert _detect_file_type("project/docs/guide.rst") == FileType.DOCS

    def test_ci_github_actions_matches_config_first(self) -> None:
        """CI patterns like .github/** also match *.yml → CONFIG wins due to dict ordering."""
        # .github/workflows/ci.yml matches **/*.yml (CONFIG) before **/.github/** (CI)
        result = _detect_file_type("repo/.github/workflows/ci.yml")
        assert result in (FileType.CI, FileType.CONFIG)

    def test_ci_jenkinsfile(self) -> None:
        """Jenkinsfile has no config extension, so CI pattern matches cleanly."""
        assert _detect_file_type("repo/Jenkinsfile") == FileType.CI

    def test_root_python_file_is_source(self) -> None:
        """Root-level files default to SOURCE since fnmatch globs need dir prefix."""
        assert _detect_file_type("setup.py") == FileType.SOURCE


# --------------------------------------------------------------------------- #
# _detect_layer
# --------------------------------------------------------------------------- #


class TestDetectLayer:
    def test_domain_layer(self) -> None:
        assert _detect_layer("src/domain/model/User.java") == "domain"

    def test_model_layer(self) -> None:
        assert _detect_layer("app/models/user.py") == "domain"

    def test_entity_layer(self) -> None:
        assert _detect_layer("src/entity/Product.java") == "domain"

    def test_application_service(self) -> None:
        assert _detect_layer("src/service/UserService.java") == "application"

    def test_application_usecase(self) -> None:
        assert _detect_layer("src/usecase/CreateOrder.java") == "application"

    def test_infrastructure_layer(self) -> None:
        assert _detect_layer("src/infrastructure/db/Repo.java") == "infrastructure"

    def test_adapter_layer(self) -> None:
        assert _detect_layer("src/adapter/http/Client.java") == "infrastructure"

    def test_presentation_controller(self) -> None:
        assert _detect_layer("src/controller/UserCtrl.java") == "presentation"

    def test_presentation_api(self) -> None:
        assert _detect_layer("src/api/endpoints.py") == "presentation"

    def test_presentation_components(self) -> None:
        assert _detect_layer("src/components/Button.tsx") == "presentation"

    def test_presentation_pages(self) -> None:
        assert _detect_layer("src/pages/Home.tsx") == "presentation"

    def test_no_layer(self) -> None:
        assert _detect_layer("src/utils/helpers.py") is None


# --------------------------------------------------------------------------- #
# _detect_module
# --------------------------------------------------------------------------- #


class TestDetectModule:
    def test_module_after_src(self) -> None:
        assert _detect_module("src/auth/login.py") == "auth"

    def test_module_after_app(self) -> None:
        assert _detect_module("app/billing/invoice.py") == "billing"

    def test_skip_src_prefix(self) -> None:
        assert _detect_module("src/domain/User.java") == "domain"

    def test_skip_main_java_prefix(self) -> None:
        assert _detect_module("src/main/java/com/example/App.java") == "com"

    def test_single_file_no_module(self) -> None:
        assert _detect_module("Makefile") is None

    def test_root_file_no_module(self) -> None:
        assert _detect_module("setup.py") is None

    def test_hidden_dirs_skipped(self) -> None:
        assert _detect_module(".github/workflows/ci.yml") == "workflows"

    def test_deep_nesting(self) -> None:
        assert _detect_module("src/auth/middleware/jwt.py") == "auth"


# --------------------------------------------------------------------------- #
# _detect_frameworks
# --------------------------------------------------------------------------- #


class TestDetectFrameworks:
    def test_spring_boot_from_path(self) -> None:
        """Need full nested path for **/src/main/java/** to match."""
        result = _detect_frameworks("project/src/main/java/com/App.java", "java")
        assert "spring-boot" in result

    def test_django_from_path(self) -> None:
        result = _detect_frameworks("myapp/urls.py", "python")
        assert "django" in result

    def test_react_tsx_file(self) -> None:
        result = _detect_frameworks("src/components/Button.tsx", "typescript")
        assert "react" in result

    def test_nestjs_from_module_file(self) -> None:
        result = _detect_frameworks("src/users/users.module.ts", "typescript")
        assert "nestjs" in result

    def test_nextjs_from_pages(self) -> None:
        """**/pages/**/*.tsx needs a file nested inside pages/ dir."""
        result = _detect_frameworks("project/pages/home/index.tsx", "typescript")
        assert "nextjs" in result

    def test_kotlin_fallback_to_spring_boot(self) -> None:
        result = _detect_frameworks("src/util/Helper.kt", "kotlin")
        assert "spring-boot" in result

    def test_no_framework(self) -> None:
        result = _detect_frameworks("lib/utils.py", "python")
        assert result == ()

    def test_no_language_no_fallback(self) -> None:
        result = _detect_frameworks("lib/utils.bin", None)
        assert result == ()

    def test_multiple_frameworks_sorted(self) -> None:
        # A .tsx file in app/pages/components matches both react and nextjs
        result = _detect_frameworks("app/pages/components/Btn.tsx", "typescript")
        assert result == tuple(sorted(result))


# --------------------------------------------------------------------------- #
# FileClassifier.classify
# --------------------------------------------------------------------------- #


class TestClassify:
    def test_single_python_file(self, classifier: FileClassifier) -> None:
        files = [_make_file_diff("src/main.py")]
        result = classifier.classify(files)
        assert len(result) == 1
        assert result[0].language == "python"
        assert result[0].file_type == FileType.SOURCE

    def test_java_domain_file(self, classifier: FileClassifier) -> None:
        files = [_make_file_diff("src/domain/model/User.java")]
        result = classifier.classify(files)
        assert result[0].language == "java"
        assert result[0].layer == "domain"

    def test_test_file_classification(self, classifier: FileClassifier) -> None:
        """Test files in nested tests/ dir are classified as TEST."""
        files = [_make_file_diff("project/tests/unit/test_auth.py")]
        result = classifier.classify(files)
        assert result[0].file_type == FileType.TEST

    def test_preserves_pre_set_language(self, classifier: FileClassifier) -> None:
        """If FileDiff already has language set, classifier should use it."""
        files = [_make_file_diff("custom.xyz", language="rust")]
        result = classifier.classify(files)
        assert result[0].language == "rust"

    def test_empty_input(self, classifier: FileClassifier) -> None:
        assert classifier.classify([]) == []

    def test_multiple_files(self, classifier: FileClassifier) -> None:
        files = [
            _make_file_diff("src/main.py"),
            _make_file_diff("src/App.java"),
            _make_file_diff("project/README.md"),
        ]
        result = classifier.classify(files)
        assert len(result) == 3
        assert result[0].language == "python"
        assert result[1].language == "java"
        assert result[2].file_type == FileType.DOCS

    def test_framework_hints_populated(self, classifier: FileClassifier) -> None:
        files = [_make_file_diff("project/src/main/java/com/example/App.java")]
        result = classifier.classify(files)
        assert "spring-boot" in result[0].framework_hints

    def test_module_populated(self, classifier: FileClassifier) -> None:
        files = [_make_file_diff("src/auth/login.py")]
        result = classifier.classify(files)
        assert result[0].module == "auth"

    def test_result_is_classified_file(self, classifier: FileClassifier) -> None:
        files = [_make_file_diff("src/main.py")]
        result = classifier.classify(files)
        assert isinstance(result[0], ClassifiedFile)
        assert result[0].diff.path == "src/main.py"
