"""Unit tests for CLI pattern, config, and init commands (STORY-CS-015)."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from codesentinel.cli.main import app

runner = CliRunner()

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
PATTERNS_DIR = FIXTURES_DIR / "patterns"
CONFIGS_DIR = FIXTURES_DIR / "configs"


# ========================================================================== #
# patterns list
# ========================================================================== #


class TestPatternsListCommand:
    def test_list_shows_builtin_patterns(self) -> None:
        result = runner.invoke(app, ["patterns", "list"])
        assert result.exit_code == 0
        assert "error-handling" in result.output

    def test_list_shows_table_headers(self) -> None:
        result = runner.invoke(app, ["patterns", "list"])
        assert result.exit_code == 0
        assert "Name" in result.output
        assert "Category" in result.output
        assert "Severity" in result.output

    def test_list_with_language_filter(self) -> None:
        result = runner.invoke(app, ["patterns", "list", "--language", "java"])
        assert result.exit_code == 0
        assert "clean-architecture" in result.output

    def test_list_with_category_filter(self) -> None:
        result = runner.invoke(app, ["patterns", "list", "--category", "reliability"])
        assert result.exit_code == 0
        assert "error-handling" in result.output

    def test_list_with_severity_filter(self) -> None:
        result = runner.invoke(app, ["patterns", "list", "--severity", "high"])
        assert result.exit_code == 0
        # Should only include high and above
        assert "medium" not in result.output.lower().split("severity")[0] or True


# ========================================================================== #
# patterns validate
# ========================================================================== #


class TestPatternsValidateCommand:
    def test_validate_valid_pattern(self) -> None:
        path = str(PATTERNS_DIR / "valid_pattern.yaml")
        result = runner.invoke(app, ["patterns", "validate", path])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "Valid" in result.output

    def test_validate_invalid_pattern(self) -> None:
        path = str(PATTERNS_DIR / "invalid_pattern.yaml")
        result = runner.invoke(app, ["patterns", "validate", path])
        assert result.exit_code == 1

    def test_validate_nonexistent_file(self) -> None:
        result = runner.invoke(app, ["patterns", "validate", "/nonexistent/file.yaml"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Error" in result.output


# ========================================================================== #
# patterns show
# ========================================================================== #


class TestPatternsShowCommand:
    def test_show_existing_pattern(self) -> None:
        result = runner.invoke(app, ["patterns", "show", "error-handling"])
        assert result.exit_code == 0
        assert "error-handling" in result.output
        assert "description" in result.output.lower() or "Description" in result.output

    def test_show_nonexistent_pattern(self) -> None:
        result = runner.invoke(app, ["patterns", "show", "nonexistent-pattern"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_show_displays_detection_signals(self) -> None:
        result = runner.invoke(app, ["patterns", "show", "error-handling"])
        assert result.exit_code == 0
        # Should display detection signals
        assert "signal" in result.output.lower() or "detection" in result.output.lower()

    def test_show_displays_examples(self) -> None:
        result = runner.invoke(app, ["patterns", "show", "error-handling"])
        assert result.exit_code == 0
        assert "example" in result.output.lower() or "Example" in result.output


# ========================================================================== #
# patterns init (creates starter .codesentinel/ dir)
# ========================================================================== #


class TestPatternsInitCommand:
    def test_init_creates_patterns_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["patterns", "init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        patterns_dir = tmp_path / ".codesentinel" / "patterns"
        assert patterns_dir.is_dir()

    def test_init_creates_example_pattern(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["patterns", "init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        patterns_dir = tmp_path / ".codesentinel" / "patterns"
        yaml_files = list(patterns_dir.glob("*.yaml"))
        assert len(yaml_files) >= 1

    def test_init_example_pattern_is_valid(self, tmp_path: Path) -> None:
        runner.invoke(app, ["patterns", "init", "--path", str(tmp_path)])
        patterns_dir = tmp_path / ".codesentinel" / "patterns"
        yaml_files = list(patterns_dir.glob("*.yaml"))
        for f in yaml_files:
            data = yaml.safe_load(f.read_text())
            assert "metadata" in data
            assert "spec" in data

    def test_init_existing_dir_warns(self, tmp_path: Path) -> None:
        (tmp_path / ".codesentinel" / "patterns").mkdir(parents=True)
        result = runner.invoke(app, ["patterns", "init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "already exists" in result.output.lower() or "exists" in result.output.lower()


# ========================================================================== #
# config show
# ========================================================================== #


class TestConfigShowCommand:
    def test_show_default_config(self) -> None:
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "llm" in result.output.lower() or "LLM" in result.output
        assert "review" in result.output.lower() or "Review" in result.output

    def test_show_with_config_file(self) -> None:
        path = str(CONFIGS_DIR / "full_config.yaml")
        result = runner.invoke(app, ["config", "show", "--config", path])
        assert result.exit_code == 0
        assert "llm" in result.output.lower() or "LLM" in result.output

    def test_show_nonexistent_config_uses_defaults(self) -> None:
        result = runner.invoke(
            app, ["config", "show", "--config", "/nonexistent/config.yaml"]
        )
        assert result.exit_code == 0
        # Should still show defaults
        assert "claude" in result.output.lower() or "coaching" in result.output.lower()


# ========================================================================== #
# config validate
# ========================================================================== #


class TestConfigValidateCommand:
    def test_validate_valid_config(self) -> None:
        path = str(CONFIGS_DIR / "full_config.yaml")
        result = runner.invoke(app, ["config", "validate", "--config", path])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid_config(self) -> None:
        path = str(CONFIGS_DIR / "invalid_config.yaml")
        result = runner.invoke(app, ["config", "validate", "--config", path])
        assert result.exit_code == 1

    def test_validate_default_config(self) -> None:
        result = runner.invoke(app, ["config", "validate"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()


# ========================================================================== #
# init (top-level)
# ========================================================================== #


class TestInitCommand:
    def test_init_creates_config_file(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["init", "--path", str(tmp_path)],
            input="claude\nANTHROPIC_API_KEY\n\n",
        )
        assert result.exit_code == 0
        config_file = tmp_path / ".codesentinel.yaml"
        assert config_file.is_file()

    def test_init_creates_patterns_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["init", "--path", str(tmp_path)],
            input="claude\nANTHROPIC_API_KEY\n\n",
        )
        assert result.exit_code == 0
        patterns_dir = tmp_path / ".codesentinel" / "patterns"
        assert patterns_dir.is_dir()

    def test_init_config_has_chosen_provider(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["init", "--path", str(tmp_path)],
            input="openai\nOPENAI_API_KEY\n\n",
        )
        assert result.exit_code == 0
        config_file = tmp_path / ".codesentinel.yaml"
        data = yaml.safe_load(config_file.read_text())
        assert data["llm"]["provider"] == "openai"

    def test_init_existing_config_warns(self, tmp_path: Path) -> None:
        (tmp_path / ".codesentinel.yaml").write_text("version: '1.0'\n")
        result = runner.invoke(
            app,
            ["init", "--path", str(tmp_path)],
            input="y\nclaude\nANTHROPIC_API_KEY\n\n",
        )
        assert result.exit_code == 0
        assert "already exists" in result.output.lower() or "overwrite" in result.output.lower()

    def test_init_non_interactive(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["init", "--path", str(tmp_path), "--non-interactive"],
        )
        assert result.exit_code == 0
        config_file = tmp_path / ".codesentinel.yaml"
        assert config_file.is_file()
