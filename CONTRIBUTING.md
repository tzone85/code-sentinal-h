# Contributing to CodeSentinel

See [docs/contributing.md](docs/contributing.md) for the full contribution guide, including development setup, PR process, and coding standards.

## Quick Start

```bash
git clone https://github.com/tzone85/code-sentinal-h.git
cd code-sentinal-h
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest tests/
```

## Commit Format

```
<type>: <description>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`
