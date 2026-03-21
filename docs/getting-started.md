# Getting Started

This guide walks you through installing CodeSentinel, running your first review, and understanding the results.

## Prerequisites

- Python 3.11 or later
- An LLM provider API key (Claude, OpenAI, or local Ollama)

## Installation

```bash
pip install codesentinel
```

## Set Up Your API Key

Choose your LLM provider and export the API key:

```bash
# Claude (recommended)
export ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
export OPENAI_API_KEY=sk-...

# Ollama (no key needed — runs locally)
# Just ensure ollama is running: ollama serve
```

## Initialize Your Project

Run `codesentinel init` in your repository root to create a starter config:

```bash
cd your-repo
codesentinel init
```

This creates:
- `.codesentinel.yaml` — repository configuration
- `.codesentinel/patterns/` — directory for custom patterns

## Run Your First Review

### Review staged changes

```bash
git add .
codesentinel review --staged
```

### Review a diff file

```bash
git diff main..feature > changes.patch
codesentinel review --diff changes.patch
```

### Review a branch

```bash
codesentinel review --branch feature/my-feature --base main
```

### Review a GitHub PR

```bash
export GITHUB_TOKEN=ghp_...
codesentinel review --pr https://github.com/org/repo/pull/123
```

## Understanding Results

CodeSentinel reports findings with five severity levels:

| Severity | Meaning | Example |
|----------|---------|---------|
| CRITICAL | Security vulnerability or data loss risk | Hardcoded API key, SQL injection |
| HIGH | Significant architectural violation | Missing input validation, broken layer boundary |
| MEDIUM | Convention or best practice violation | Inconsistent naming, missing error handling |
| LOW | Minor style or improvement suggestion | Verbose code that could be simplified |
| INFO | Informational observation | Unused import, documentation gap |

Each finding includes:
- **File and line** — exact location in the diff
- **Pattern name** — which pattern detected the issue
- **Description** — what the issue is
- **Remediation** — how to fix it

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No findings at or above the configured severity threshold |
| 1 | Findings found — review needed |
| 2 | Invalid arguments or configuration |
| 3 | Runtime error |

## Next Steps

- [Configuration](configuration.md) — customize settings for your project
- [Writing Patterns](writing-patterns.md) — create custom review patterns
- [CLI Reference](cli.md) — all commands and flags
- [LLM Providers](llm-providers.md) — provider-specific setup
