# CLI Reference

CodeSentinel is invoked via the `codesentinel` command. All commands use the Typer framework with Rich formatting.

## Global Options

```bash
codesentinel --help     # Show help
codesentinel --version  # Show version
```

## `review` — Review Code Changes

The main command. Analyzes diffs against patterns using an LLM.

```bash
codesentinel review [OPTIONS]
```

### Input Sources (mutually exclusive)

| Flag | Description |
|------|-------------|
| `--diff PATH` | Review a diff file (unified format) |
| `--branch NAME` | Review a branch against base |
| `--pr URL` | Review a pull request (requires SCM token) |
| `--staged` | Review staged (git add) changes |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--base BRANCH` | `main` | Base branch for comparison |
| `--repo PATH` | `.` | Repository path |
| `--config PATH` | `.codesentinel.yaml` | Config file path |
| `--severity LEVEL` | `medium` | Minimum severity to report (`critical`, `high`, `medium`, `low`, `info`) |
| `--format FORMAT` | `terminal` | Output format (`terminal`, `json`, `sarif`) |
| `--verbose` | `false` | Enable verbose output (shows rationale and remediation) |
| `--dry-run` | `false` | Show resolved config without running the review |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No findings at or above `fail_on` severity |
| 1 | Findings found at or above `fail_on` severity |
| 2 | Invalid arguments or configuration |
| 3 | Runtime error |

### Examples

```bash
# Review a patch file, show only high+ severity
codesentinel review --diff changes.patch --severity high

# Review staged changes with verbose output
codesentinel review --staged --verbose

# Review a GitHub PR, output as JSON
export GITHUB_TOKEN=ghp_...
codesentinel review --pr https://github.com/org/repo/pull/42 --format json

# Dry run — show config without reviewing
codesentinel review --diff changes.patch --dry-run
```

## `patterns` — Manage Patterns

### `patterns list`

List available patterns with optional filters.

```bash
codesentinel patterns list [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--language LANG` | Filter by target language |
| `--category CAT` | Filter by category |
| `--severity LEVEL` | Filter by minimum severity |

### `patterns show`

Show full details of a specific pattern.

```bash
codesentinel patterns show PATTERN_NAME
```

### `patterns validate`

Validate a pattern YAML file against the schema.

```bash
codesentinel patterns validate PATH
```

### `patterns init`

Create a starter patterns directory with example pattern.

```bash
codesentinel patterns init [--path DIR]
```

## `config` — Manage Configuration

### `config show`

Show the resolved configuration (all tiers merged).

```bash
codesentinel config show [--config PATH]
```

### `config validate`

Validate a configuration file against the schema.

```bash
codesentinel config validate [--config PATH]
```

## `init` — Initialize Project

Create a `.codesentinel/` directory with starter config and patterns.

```bash
codesentinel init
```

## `version` — Show Version

```bash
codesentinel version
```
