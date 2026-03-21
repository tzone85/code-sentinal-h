# Contributing to CodeSentinel

Thank you for your interest in contributing. This guide covers the development setup, contribution process, and guidelines.

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Clone and Install

```bash
git clone https://github.com/tzone85/code-sentinal-h.git
cd code-sentinal-h
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/                      # All tests
pytest tests/unit/                 # Unit tests only
pytest tests/ --cov=codesentinel   # With coverage
```

### Run Linting

```bash
ruff check src/ tests/             # Lint check
ruff format src/ tests/            # Format check
```

### Type Checking

```bash
mypy src/codesentinel/
```

## Contribution Process

1. **Fork** the repository
2. **Create a branch** from `main`: `git checkout -b feature/my-change`
3. **Write tests first** — follow TDD (Red → Green → Refactor)
4. **Implement** your changes
5. **Run the full test suite** and linting before committing
6. **Commit** with a conventional commit message: `feat: add X`, `fix: resolve Y`
7. **Push** and open a pull request against `main`

## Commit Message Format

```
<type>: <description>

<optional body>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

## Code Standards

- **Immutability** — use frozen dataclasses and Pydantic models with `frozen=True`
- **Small files** — 200–400 lines typical, 800 max
- **Small functions** — under 50 lines
- **Type hints** — all public APIs must have type annotations
- **Error handling** — handle errors explicitly, never swallow silently
- **Test coverage** — maintain 80%+ coverage

## Contributing Patterns

Custom patterns are welcome. To add a new built-in pattern:

1. Create a YAML file in `src/codesentinel/patterns/builtin/<language>/`
2. Follow the schema in [Writing Patterns](writing-patterns.md)
3. Validate with `codesentinel patterns validate your-pattern.yaml`
4. Add tests that verify detection against known-good and known-bad diffs
5. Open a PR with the pattern and its tests

## Project Structure

```
src/codesentinel/
├── cli/          # CLI entry point
├── config/       # Configuration system
├── core/         # Pipeline engine
├── llm/          # LLM providers
├── patterns/     # Pattern system
├── reporters/    # Output reporters
└── scm/          # SCM integrations

tests/
├── unit/         # Unit tests
├── integration/  # Integration tests (require API keys)
└── e2e/          # End-to-end tests
```

## Questions?

Open an issue on GitHub for questions, bug reports, or feature requests.
