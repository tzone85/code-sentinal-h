# CodeSentinel

AI-powered code review tool that enforces architectural patterns and best practices through LLM analysis of diffs.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)

## What It Does

CodeSentinel reviews code changes (diffs, branches, PRs, staged files) against a library of configurable patterns. It uses LLMs to detect violations of architectural rules, security practices, and coding standards — then reports findings in your terminal, as PR comments, or in SARIF/JSON format.

**Key features:**

| Feature | Description |
|---------|-------------|
| Pattern-based review | 16 built-in patterns for Java, Python, TypeScript, and general best practices |
| Multi-LLM support | Claude (Anthropic), OpenAI, and Ollama (local) |
| Multi-SCM support | GitHub, GitLab, Azure DevOps, Bitbucket, and local Git |
| Multiple output formats | Terminal (Rich), JSON, SARIF, inline PR comments |
| 3-tier config | Built-in defaults, user config, and repo config with deep merge |
| Custom patterns | Write your own YAML patterns with detection signals and examples |
| CI/CD ready | GitHub Action, configurable exit codes, SARIF for IDE integration |

## Installation

```bash
pip install codesentinel
```

Or install from source:

```bash
git clone https://github.com/tzone85/code-sentinal-h.git
cd code-sentinal-h
pip install -e ".[dev]"
```

### Prerequisites

- Python 3.11 or later
- Works on **macOS, Linux, and Windows**
- An API key for your chosen LLM provider:

**macOS / Linux:**

```bash
export ANTHROPIC_API_KEY=your-key   # Claude
export OPENAI_API_KEY=your-key      # OpenAI
# Ollama — no key needed
```

**Windows (PowerShell):**

```powershell
$env:ANTHROPIC_API_KEY = "your-key"   # Claude
$env:OPENAI_API_KEY = "your-key"      # OpenAI
# Ollama — no key needed
```

> **Windows users:** See [Windows Setup](docs/getting-started.md#windows-specific-setup) for PATH, encoding, and proxy troubleshooting.

## Quick Start

### 1. Initialize a project

```bash
codesentinel init
```

This creates a `.codesentinel/` directory with a starter config and patterns directory.

### 2. Review a diff file

```bash
codesentinel review --diff changes.patch
```

### 3. Review staged changes

```bash
codesentinel review --staged
```

### 4. Review a branch

```bash
codesentinel review --branch feature/my-feature --base main
```

### 5. Review a GitHub PR

```bash
export GITHUB_TOKEN=your-token
codesentinel review --pr https://github.com/org/repo/pull/123
```

### Example Output

```
╭──────────────────────── CodeSentinel Review ────────────────────────╮
│ Target: feature/add-auth (vs main)                                  │
│ Files: 4 reviewed | Patterns: 8 loaded, 3 matched                  │
╰─────────────────────────────────────────────────────────────────────╯

[!] CRITICAL  src/auth/handler.py:42
    Hardcoded API key detected
    Pattern: security-no-hardcoded-secrets
    Remediation: Move the secret to an environment variable or secret manager.

[H] HIGH  src/api/routes.py:87
    Missing input validation on user-supplied data
    Pattern: security-basics
    Remediation: Add schema validation before processing the request body.

Summary: 2 findings (1 critical, 1 high) | 0.8s elapsed
```

## Usage

See the [CLI Reference](docs/cli.md) for all commands and flags.

### Review modes

| Mode | Behavior |
|------|----------|
| `coaching` (default) | Explains issues with educational context |
| `strict` | Concise findings, higher confidence threshold |
| `gatekeeping` | Blocks PRs on critical/high findings |

### Output formats

```bash
# Terminal (default)
codesentinel review --diff changes.patch

# JSON report
codesentinel review --diff changes.patch --format json

# SARIF (for IDE integration)
codesentinel review --diff changes.patch --format sarif
```

### Managing patterns

```bash
# List all available patterns
codesentinel patterns list

# Filter by language
codesentinel patterns list --language python

# Show pattern details
codesentinel patterns show security-no-hardcoded-secrets

# Validate a custom pattern
codesentinel patterns validate my-pattern.yaml
```

### Configuration

```bash
# Show resolved config (all tiers merged)
codesentinel config show

# Validate config file
codesentinel config validate
```

## Documentation

- [Getting Started](docs/getting-started.md) — Installation, first review, basic concepts
- [Architecture](docs/architecture.md) — Pipeline overview, component diagram, data flow
- [Configuration](docs/configuration.md) — Full config reference with all options
- [Writing Patterns](docs/writing-patterns.md) — Guide for custom pattern authors
- [CLI Reference](docs/cli.md) — All commands, flags, and exit codes
- [LLM Providers](docs/llm-providers.md) — Setup guide for Claude, OpenAI, Ollama
- [SCM Integrations](docs/scm-integrations.md) — GitHub, GitLab, Azure DevOps, Bitbucket setup
- [GitHub Action](docs/github-action.md) — CI/CD integration guide
- [Contributing](CONTRIBUTING.md) — Development setup, PR process, pattern contributions

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
