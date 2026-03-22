# Configuration Reference

CodeSentinel uses a 3-tier configuration system with deep merge. Higher-priority tiers override lower-priority values while preserving keys that only exist in lower tiers.

## Configuration Priority

1. **Repository config** (`.codesentinel.yaml` in repo root) — highest priority
2. **User config** (`~/.config/codesentinel/config.yaml` or `CODESENTINEL_USER_CONFIG` env var)
3. **Built-in defaults** — lowest priority

## Minimal Config

A working config needs only a provider. Everything else has sensible defaults:

```yaml
version: "1.0"
llm:
  provider: "claude"
```

## Full Config Reference

```yaml
version: "1.0"

# ─── LLM Provider ────────────────────────────────────
llm:
  provider: "claude"              # claude | openai | ollama
  model: "claude-sonnet-4-20250514"  # Model name (provider-specific)
  max_tokens: 4096                # Max tokens per LLM response (1–∞)
  temperature: 0.2                # Sampling temperature (0.0–2.0)
  max_concurrent_requests: 3      # Parallel LLM calls (1–∞)

  # Provider-specific options (passed through)
  claude: {}
  openai: {}
  ollama: {}

# ─── Review Settings ─────────────────────────────────
review:
  min_severity: "medium"          # Minimum severity to report
                                  # critical | high | medium | low | info
  max_findings: 15                # Maximum findings to return (1–∞)
  min_confidence: 0.7             # Minimum confidence threshold (0.0–1.0)
  mode: "coaching"                # coaching | strict | gatekeeping

  focus: []                       # Pattern names to focus on (empty = all)
  ignore:                         # File globs to skip
    - "*.lock"
    - "*.min.js"
    - "*.min.css"
    - "*.map"
    - "*.snap"
    - "*.svg"
    - "*.png"
    - "*.jpg"
    - "*.gif"
    - "*.ico"
    - "*.woff"
    - "*.woff2"
    - "*.ttf"
    - "*.eot"
    - "package-lock.json"
    - "yarn.lock"
    - "pnpm-lock.yaml"
    - "poetry.lock"
    - "Pipfile.lock"
    - "go.sum"
    - "Cargo.lock"

  additional_context:             # Extra docs for LLM context
    - path: "/path/to/architecture.md"
      description: "Architecture overview"

# ─── Patterns ────────────────────────────────────────
patterns:
  builtin:
    enabled: true                 # Load built-in patterns
    include: []                   # Names to include (empty = all)
    exclude: []                   # Names to exclude

  remote:                         # Git-hosted pattern repos
    - repo: "https://github.com/org/patterns.git"
      path: "patterns/"
      ref: "main"
      cache_ttl: 3600             # Cache duration in seconds

  local:                          # Local pattern directories
    - ".codesentinel/patterns/"

# ─── Reporters ───────────────────────────────────────
reporters:
  terminal:
    enabled: true
    color: true
    verbose: false

  github:
    enabled: false
    post_review: true
    request_changes_on: "critical"  # Severity that triggers request_changes
    comment_style: "both"           # inline | summary | both

  gitlab:
    enabled: false
    post_review: true
    request_changes_on: "critical"
    comment_style: "both"

  azure_devops:
    enabled: false
    post_review: true
    request_changes_on: "critical"
    comment_style: "both"

  json:
    enabled: false
    output_path: "codesentinel-report.json"

  sarif:
    enabled: false
    output_path: "codesentinel-report.sarif"
```

## Review Modes

| Mode | Description |
|------|-------------|
| `coaching` | Default. Provides educational explanations with findings. Best for learning teams. |
| `strict` | Concise findings with higher confidence threshold. Best for experienced teams. |
| `gatekeeping` | Blocks PRs on critical/high findings. Requests changes automatically. Best for CI enforcement. |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | API key for Claude provider |
| `OPENAI_API_KEY` | API key for OpenAI provider |
| `GITHUB_TOKEN` | Token for GitHub SCM and PR comments |
| `GITLAB_TOKEN` | Token for GitLab SCM and MR comments |
| `AZURE_DEVOPS_TOKEN` | Token for Azure DevOps SCM and PR comments |
| `BITBUCKET_TOKEN` | Token for Bitbucket SCM and PR comments |
| `CODESENTINEL_USER_CONFIG` | Override path for user-level config file |

## Deep Merge Behavior

When multiple config tiers define the same key:

- **Scalar values** — higher-priority tier wins
- **Dict values** — merged recursively (keys from both tiers are preserved)
- **List values** — higher-priority tier replaces the entire list

Example:

```yaml
# User config (~/.config/codesentinel/config.yaml)
llm:
  provider: "openai"
  temperature: 0.5

# Repo config (.codesentinel.yaml)
llm:
  temperature: 0.1
review:
  mode: "strict"
```

Resolved config:

```yaml
llm:
  provider: "openai"      # from user config
  temperature: 0.1         # repo overrides user
  model: "claude-sonnet-4-20250514"  # from defaults
  max_tokens: 4096         # from defaults
review:
  mode: "strict"           # from repo config
  min_severity: "medium"   # from defaults
```

## Validating Config

```bash
# Check current resolved config
codesentinel config show

# Validate a config file
codesentinel config validate --config .codesentinel.yaml
```
