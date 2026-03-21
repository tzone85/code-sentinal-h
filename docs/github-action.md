# GitHub Action

CodeSentinel provides a GitHub Action for automated PR reviews in CI/CD pipelines.

## Quick Setup

Add to `.github/workflows/codesentinel.yml`:

```yaml
name: CodeSentinel Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - name: CodeSentinel Review
        uses: tzone85/code-sentinal-h@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github_token` | yes | — | GitHub token for PR access and comments |
| `anthropic_api_key` | no | — | Anthropic API key (for Claude provider) |
| `openai_api_key` | no | — | OpenAI API key (for OpenAI provider) |
| `config_path` | no | `.codesentinel.yaml` | Path to config file |
| `severity` | no | `medium` | Minimum severity to report |
| `mode` | no | `coaching` | Review mode (`coaching`, `strict`, `gatekeeping`) |
| `fail_on` | no | `critical` | Severity that causes the action to fail |

## Outputs

| Output | Description |
|--------|-------------|
| `findings_count` | Total number of findings |
| `exit_code` | Review exit code (0, 1, 2, 3) |
| `report_path` | Path to JSON report file |

## Examples

### Basic Setup (Claude)

```yaml
- uses: tzone85/code-sentinal-h@main
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
```

### Strict Mode with High Severity Gate

```yaml
- uses: tzone85/code-sentinal-h@main
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
    mode: "gatekeeping"
    severity: "high"
    fail_on: "high"
```

### Using OpenAI

```yaml
- uses: tzone85/code-sentinal-h@main
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    openai_api_key: ${{ secrets.OPENAI_API_KEY }}
```

### Custom Config

```yaml
- uses: tzone85/code-sentinal-h@main
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
    config_path: ".codesentinel/ci-config.yaml"
```

## Permissions

The action needs these GitHub permissions:

```yaml
permissions:
  contents: read         # Read repository content
  pull-requests: write   # Post review comments
```

## Troubleshooting

### Action fails with "No API key"

Ensure the API key secret is configured in your repository settings (Settings > Secrets and variables > Actions).

### Comments not appearing on PR

Check that:
1. `pull-requests: write` permission is set
2. `github_token` has sufficient scope
3. The PR is not from a fork (fork PRs have restricted token permissions)

### Review takes too long

Large PRs with many files may take longer. Consider:
- Increasing `max_concurrent_requests` in your config
- Setting a higher `min_severity` to reduce LLM calls
- Adding ignore globs for generated or vendor files
