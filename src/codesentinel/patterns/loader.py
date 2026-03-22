"""Load patterns from builtin, local, and remote sources."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from codesentinel.core.exceptions import PatternError
from codesentinel.patterns.schema import Pattern
from codesentinel.patterns.validator import validate_pattern

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "codesentinel" / "patterns"
_DEFAULT_CACHE_TTL = 3600  # seconds


def _hash_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load_yaml_file(path: Path) -> dict[str, Any]:
    """Read and parse a single YAML file, raising PatternError on failure."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as exc:
        msg = f"Failed to read pattern file {path}: {exc}"
        raise PatternError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Pattern file {path} does not contain a YAML mapping"
        raise PatternError(msg)
    return data


def _parse_pattern(data: dict[str, Any], source: str) -> Pattern:
    """Parse a dict into a Pattern, raising PatternError on validation failure."""
    try:
        return Pattern.model_validate(data)
    except Exception as exc:
        msg = f"Invalid pattern from {source}: {exc}"
        raise PatternError(msg) from exc


class PatternLoader:
    """Loads and merges patterns from multiple sources."""

    def __init__(self, cache_dir: Path | None = None, cache_ttl: int = _DEFAULT_CACHE_TTL) -> None:
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._cache_ttl = cache_ttl

    def load_all(self, config: dict[str, Any]) -> list[Pattern]:
        """Load patterns from all configured sources, merging by name.

        Merge order: builtin → remote → local (last wins on name collision).
        """
        patterns_by_name: dict[str, Pattern] = {}

        # 1. Builtin patterns
        builtin_cfg = config.get("builtin", {})
        if builtin_cfg.get("enabled", True):
            include = builtin_cfg.get("include", [])
            for p in self.load_builtin(include):
                patterns_by_name[p.metadata.name] = p

        # 2. Remote patterns
        for remote in config.get("remote", []):
            repo = remote.get("repo", "")
            path = remote.get("path", "patterns")
            ref = remote.get("ref", "main")
            ttl = remote.get("cache_ttl", self._cache_ttl)
            for p in self.load_remote(repo, path, ref, cache_ttl=ttl):
                patterns_by_name[p.metadata.name] = p

        # 3. Local patterns
        local_paths = config.get("local", [])
        for p in self.load_local(local_paths):
            patterns_by_name[p.metadata.name] = p

        return list(patterns_by_name.values())

    def load_builtin(self, include: list[str] | None = None) -> list[Pattern]:
        """Load patterns shipped with the codesentinel package."""
        patterns: list[Pattern] = []
        try:
            builtin_pkg = importlib.resources.files("codesentinel.patterns.builtin")
        except (ModuleNotFoundError, TypeError):
            logger.warning("Builtin patterns package not found")
            return patterns

        yaml_files = _collect_yaml_files_from_traversable(builtin_pkg)
        for entry in yaml_files:
            try:
                raw = entry.read_text(encoding="utf-8")
                data = yaml.safe_load(raw)
                if not isinstance(data, dict):
                    continue
                pattern = _parse_pattern(data, f"builtin:{entry.name}")
                if include and pattern.metadata.name not in include:
                    continue
                patterns.append(pattern)
            except PatternError as exc:
                logger.warning("Skipping invalid builtin pattern %s: %s", entry.name, exc)
        return patterns

    def load_local(self, paths: list[str]) -> list[Pattern]:
        """Load patterns from local filesystem paths."""
        patterns: list[Pattern] = []
        for raw_path in paths:
            p = Path(raw_path).expanduser()
            if not p.exists():
                logger.warning("Local pattern path does not exist: %s", p)
                continue
            yaml_files = list(p.rglob("*.yaml")) + list(p.rglob("*.yml"))
            for f in yaml_files:
                try:
                    data = _load_yaml_file(f)
                    pattern = _parse_pattern(data, str(f))
                    warnings = validate_pattern(pattern)
                    for w in warnings:
                        logger.warning("Pattern %s: %s", pattern.metadata.name, w)
                    patterns.append(pattern)
                except PatternError as exc:
                    logger.warning("Skipping invalid local pattern %s: %s", f, exc)
        return patterns

    def load_remote(
        self,
        repo: str,
        path: str = "patterns",
        ref: str = "main",
        *,
        cache_ttl: int | None = None,
    ) -> list[Pattern]:
        """Load patterns from a remote repository with local caching.

        Uses SHA256-based cache keys and TTL-based expiry.
        Falls back to stale cache on network failure.
        """
        ttl = cache_ttl if cache_ttl is not None else self._cache_ttl
        cache_key = _hash_key(f"{repo}:{path}:{ref}")
        cache_file = self._cache_dir / f"{cache_key}.json"

        # Try loading from cache if fresh
        cached = self._read_cache(cache_file, ttl)
        if cached is not None:
            return cached

        # Attempt network fetch (placeholder — actual git clone / API call is
        # not implemented here; teams would override or inject a fetcher)
        try:
            fetched = self._fetch_remote(repo, path, ref)
            self._write_cache(cache_file, fetched)
            return fetched
        except Exception as exc:
            logger.warning("Failed to fetch remote patterns from %s: %s", repo, exc)
            # Fall back to stale cache
            stale = self._read_cache(cache_file, ttl=None)
            if stale is not None:
                logger.info("Using stale cache for %s", repo)
                return stale
            return []

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _read_cache(self, cache_file: Path, ttl: int | None) -> list[Pattern] | None:
        if not cache_file.exists():
            return None
        try:
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            if ttl is not None:
                cached_at = raw.get("cached_at", 0)
                if time.time() - cached_at > ttl:
                    return None
            return [Pattern.model_validate(p) for p in raw.get("patterns", [])]
        except Exception as exc:
            logger.warning("Cache read failed for %s: %s", cache_file, exc)
            return None

    def _write_cache(self, cache_file: Path, patterns: list[Pattern]) -> None:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "cached_at": time.time(),
                "patterns": [p.model_dump(by_alias=True) for p in patterns],
            }
            cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Cache write failed: %s", exc)

    def _fetch_remote(self, repo: str, path: str, ref: str) -> list[Pattern]:
        """Fetch patterns from a remote git repository.

        This is a placeholder that raises NotImplementedError.
        Concrete implementations can use git clone, GitHub API, etc.
        """
        msg = f"Remote fetching not yet implemented for {repo}:{path}@{ref}"
        raise NotImplementedError(msg)


def _collect_yaml_files_from_traversable(root: Any) -> list[Any]:
    """Recursively collect .yaml/.yml files from an importlib Traversable."""
    results: list[Any] = []
    try:
        for entry in root.iterdir():
            if entry.is_file() and (entry.name.endswith(".yaml") or entry.name.endswith(".yml")):
                results.append(entry)
            elif entry.is_dir():
                results.extend(_collect_yaml_files_from_traversable(entry))
    except (TypeError, AttributeError):
        pass
    return results
