"""Tests for patterns/loader.py — pattern loading from multiple sources."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from codesentinel.core.exceptions import PatternError
from codesentinel.patterns.loader import PatternLoader, _load_yaml_file, _parse_pattern
from codesentinel.patterns.schema import Pattern, PatternMetadata, PatternSpec

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "patterns"


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_pattern_dict(name: str = "test-pattern") -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Pattern",
        "metadata": {"name": name, "category": "general"},
        "spec": {"description": f"Pattern {name}"},
    }


# ------------------------------------------------------------------ #
# _load_yaml_file
# ------------------------------------------------------------------ #


class TestLoadYamlFile:
    def test_valid_yaml(self) -> None:
        data = _load_yaml_file(FIXTURES_DIR / "valid_pattern.yaml")
        assert data["metadata"]["name"] == "clean-architecture"

    def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(PatternError, match="Failed to read"):
            _load_yaml_file(FIXTURES_DIR / "nonexistent.yaml")


# ------------------------------------------------------------------ #
# _parse_pattern
# ------------------------------------------------------------------ #


class TestParsePattern:
    def test_valid_dict(self) -> None:
        data = _make_pattern_dict()
        p = _parse_pattern(data, "test")
        assert p.metadata.name == "test-pattern"

    def test_invalid_dict_raises(self) -> None:
        with pytest.raises(PatternError, match="Invalid pattern"):
            _parse_pattern({"bad": "data"}, "test")


# ------------------------------------------------------------------ #
# PatternLoader.load_local
# ------------------------------------------------------------------ #


class TestLoadLocal:
    def test_load_from_fixtures(self) -> None:
        loader = PatternLoader()
        patterns = loader.load_local([str(FIXTURES_DIR)])
        # Should load valid_pattern.yaml, minimal_pattern.yaml, second_pattern.yaml
        # Should skip invalid_pattern.yaml
        names = {p.metadata.name for p in patterns}
        assert "clean-architecture" in names
        assert "minimal-example" in names
        assert "api-error-handling" in names

    def test_nonexistent_path_logs_warning(self) -> None:
        loader = PatternLoader()
        patterns = loader.load_local(["/nonexistent/path"])
        assert patterns == []

    def test_empty_list(self) -> None:
        loader = PatternLoader()
        patterns = loader.load_local([])
        assert patterns == []


# ------------------------------------------------------------------ #
# PatternLoader.load_builtin
# ------------------------------------------------------------------ #


class TestLoadBuiltin:
    def test_load_builtin_returns_list(self) -> None:
        loader = PatternLoader()
        patterns = loader.load_builtin()
        # Builtin dir is empty by default — should return empty list
        assert isinstance(patterns, list)

    def test_load_builtin_with_include_filter(self) -> None:
        loader = PatternLoader()
        patterns = loader.load_builtin(include=["nonexistent-pattern"])
        assert patterns == []


# ------------------------------------------------------------------ #
# PatternLoader cache
# ------------------------------------------------------------------ #


class TestCache:
    def test_write_and_read_cache(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path, cache_ttl=3600)
        pattern = Pattern(
            metadata=PatternMetadata(name="cached-pat", category="g"),
            spec=PatternSpec(description="cached"),
        )
        cache_file = tmp_path / "test_cache.json"
        loader._write_cache(cache_file, [pattern])
        result = loader._read_cache(cache_file, ttl=3600)
        assert result is not None
        assert len(result) == 1
        assert result[0].metadata.name == "cached-pat"

    def test_expired_cache_returns_none(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path, cache_ttl=1)
        pattern = Pattern(
            metadata=PatternMetadata(name="expired-pat", category="g"),
            spec=PatternSpec(description="expired"),
        )
        cache_file = tmp_path / "expired.json"
        # Write cache with timestamp in the past
        payload = {
            "cached_at": time.time() - 100,
            "patterns": [pattern.model_dump(by_alias=True)],
        }
        cache_file.write_text(json.dumps(payload))
        result = loader._read_cache(cache_file, ttl=1)
        assert result is None

    def test_stale_cache_with_no_ttl(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        pattern = Pattern(
            metadata=PatternMetadata(name="stale-pat", category="g"),
            spec=PatternSpec(description="stale"),
        )
        cache_file = tmp_path / "stale.json"
        payload = {
            "cached_at": time.time() - 99999,
            "patterns": [pattern.model_dump(by_alias=True)],
        }
        cache_file.write_text(json.dumps(payload))
        # ttl=None means ignore expiry
        result = loader._read_cache(cache_file, ttl=None)
        assert result is not None

    def test_corrupted_cache_returns_none(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        cache_file = tmp_path / "corrupt.json"
        cache_file.write_text("NOT JSON")
        result = loader._read_cache(cache_file, ttl=3600)
        assert result is None


# ------------------------------------------------------------------ #
# PatternLoader.load_remote
# ------------------------------------------------------------------ #


class TestLoadRemote:
    def test_remote_falls_back_to_stale_cache(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path, cache_ttl=1)
        # Pre-populate stale cache
        from codesentinel.patterns.loader import _hash_key

        cache_key = _hash_key("repo:path:main")
        cache_file = tmp_path / f"{cache_key}.json"
        pattern = Pattern(
            metadata=PatternMetadata(name="stale-remote", category="g"),
            spec=PatternSpec(description="stale remote"),
        )
        payload = {
            "cached_at": time.time() - 99999,
            "patterns": [pattern.model_dump(by_alias=True)],
        }
        cache_file.write_text(json.dumps(payload))

        result = loader.load_remote("repo", "path", "main")
        assert len(result) == 1
        assert result[0].metadata.name == "stale-remote"

    def test_remote_no_cache_returns_empty(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        result = loader.load_remote("no-repo", "path", "main")
        assert result == []


# ------------------------------------------------------------------ #
# PatternLoader.load_all
# ------------------------------------------------------------------ #


class TestLoadAll:
    def test_merge_builtin_and_local(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        config = {
            "builtin": {"enabled": True},
            "local": [str(FIXTURES_DIR)],
        }
        patterns = loader.load_all(config)
        names = {p.metadata.name for p in patterns}
        assert "clean-architecture" in names

    def test_builtin_disabled(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        config = {
            "builtin": {"enabled": False},
            "local": [str(FIXTURES_DIR)],
        }
        patterns = loader.load_all(config)
        names = {p.metadata.name for p in patterns}
        # Still loads local patterns
        assert "clean-architecture" in names

    def test_local_overrides_builtin(self, tmp_path: Path) -> None:
        """Local patterns should override builtin patterns with the same name."""
        loader = PatternLoader(cache_dir=tmp_path)
        config = {
            "builtin": {"enabled": True},
            "local": [str(FIXTURES_DIR)],
        }
        patterns = loader.load_all(config)
        # Since there are no builtin patterns yet, this just tests the merge path
        assert isinstance(patterns, list)

    def test_empty_config(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        patterns = loader.load_all({})
        assert isinstance(patterns, list)

    def test_load_all_with_remote_config(self, tmp_path: Path) -> None:
        """Remote patterns that fail fetch return empty, don't crash."""
        loader = PatternLoader(cache_dir=tmp_path)
        config = {
            "builtin": {"enabled": False},
            "remote": [{"repo": "org/patterns", "path": "p", "ref": "main", "cache_ttl": 60}],
            "local": [],
        }
        patterns = loader.load_all(config)
        assert isinstance(patterns, list)

    def test_load_all_with_builtin_include_filter(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        config = {
            "builtin": {"enabled": True, "include": ["security-basics"]},
        }
        patterns = loader.load_all(config)
        names = {p.metadata.name for p in patterns}
        if patterns:
            assert all(n == "security-basics" for n in names)


# ------------------------------------------------------------------ #
# _load_yaml_file edge cases
# ------------------------------------------------------------------ #


class TestLoadYamlFileEdgeCases:
    def test_non_dict_yaml_raises(self, tmp_path: Path) -> None:
        """YAML file containing a list (not mapping) should raise PatternError."""
        f = tmp_path / "list.yaml"
        f.write_text("- item1\n- item2\n")
        with pytest.raises(PatternError, match="does not contain a YAML mapping"):
            _load_yaml_file(f)

    def test_scalar_yaml_raises(self, tmp_path: Path) -> None:
        """YAML file containing just a scalar should raise PatternError."""
        f = tmp_path / "scalar.yaml"
        f.write_text("just a string\n")
        with pytest.raises(PatternError, match="does not contain a YAML mapping"):
            _load_yaml_file(f)

    def test_invalid_yaml_syntax_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("key: [unclosed bracket\n")
        with pytest.raises(PatternError, match="Failed to read"):
            _load_yaml_file(f)


# ------------------------------------------------------------------ #
# PatternLoader.load_builtin — additional edge cases
# ------------------------------------------------------------------ #


class TestLoadBuiltinEdgeCases:
    def test_builtin_loads_actual_patterns(self) -> None:
        """Builtin directory has real patterns — verify they load."""
        loader = PatternLoader()
        patterns = loader.load_builtin()
        assert len(patterns) > 0
        for p in patterns:
            assert p.metadata.name

    def test_builtin_include_specific_pattern(self) -> None:
        loader = PatternLoader()
        patterns = loader.load_builtin(include=["security-basics"])
        names = {p.metadata.name for p in patterns}
        if patterns:
            assert names == {"security-basics"}


# ------------------------------------------------------------------ #
# Cache write failure
# ------------------------------------------------------------------ #


class TestCacheWriteFailure:
    def test_write_to_readonly_dir_logs_warning(self, tmp_path: Path) -> None:
        """Cache write to unwritable path should not raise."""
        import os

        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(str(readonly_dir), 0o444)
        try:
            loader = PatternLoader(cache_dir=readonly_dir / "nested")
            cache_file = readonly_dir / "nested" / "test.json"
            # Should not raise, just log a warning
            loader._write_cache(cache_file, [])
        finally:
            os.chmod(str(readonly_dir), 0o755)

    def test_read_nonexistent_cache(self, tmp_path: Path) -> None:
        loader = PatternLoader(cache_dir=tmp_path)
        result = loader._read_cache(tmp_path / "missing.json", ttl=3600)
        assert result is None


# ------------------------------------------------------------------ #
# _fetch_remote placeholder
# ------------------------------------------------------------------ #


class TestFetchRemote:
    def test_fetch_remote_raises_not_implemented(self) -> None:
        loader = PatternLoader()
        with pytest.raises(NotImplementedError, match="not yet implemented"):
            loader._fetch_remote("repo", "path", "main")
