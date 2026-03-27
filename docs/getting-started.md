# Getting Started

This guide walks you through installing CodeSentinel, running your first review, and understanding the results.

## Prerequisites

- Python 3.11 or later
- Git
- An LLM provider API key (Claude, OpenAI, or local Ollama)

## Installation

```bash
pip install codesentinel
```

## Set Up Your API Key

Choose your LLM provider and set the API key:

### macOS / Linux

```bash
# Claude (recommended)
export ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
export OPENAI_API_KEY=sk-...

# Ollama (no key needed — runs locally)
# Just ensure ollama is running: ollama serve
```

### Windows (PowerShell)

```powershell
# Claude (recommended)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# OpenAI
$env:OPENAI_API_KEY = "sk-..."

# Ollama — no key needed, just run: ollama serve
```

To set environment variables permanently on Windows, use:

```powershell
# Persist across sessions (user-level)
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
```

Or via **Settings > System > About > Advanced system settings > Environment Variables**.

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

## Windows-Specific Setup

### Installing Python on Windows

1. Download Python 3.11+ from [python.org](https://www.python.org/downloads/)
2. **Check "Add python.exe to PATH"** during installation
3. Verify: `python --version`

### `codesentinel` command not found

Ensure Python's Scripts directory is on your PATH:

```powershell
# Run via module as a workaround
python -m codesentinel review --staged

# Or add Scripts to PATH permanently
$scriptsDir = python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
[System.Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";" + $scriptsDir, "User")
```

### Encoding issues

CodeSentinel uses UTF-8 throughout. Set this to avoid Windows encoding problems:

```powershell
# In your PowerShell profile ($PROFILE) or session
$env:PYTHONUTF8 = "1"
```

### Git diff encoding

```powershell
git config --global core.quotepath false
git config --global i18n.logoutputencoding utf-8
```

### Long path support

Windows has a 260-character path limit by default. Enable long paths:

```powershell
# Run PowerShell as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

### Corporate proxy / SSL errors

```powershell
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org codesentinel
```

### Ollama on Windows

1. Download [Ollama for Windows](https://ollama.com/download/windows)
2. Pull a model: `ollama pull llama3`
3. Configure in `.codesentinel.yaml`:

```yaml
llm:
  provider: ollama
  model: llama3
```

### SARIF + VS Code

1. Install the [SARIF Viewer](https://marketplace.visualstudio.com/items?itemName=MS-SARIFVSCode.sarif-viewer) extension
2. Run: `codesentinel review --staged --format sarif`
3. Open the generated `.sarif` file — findings appear as inline annotations

## Next Steps

- [Configuration](configuration.md) — customize settings for your project
- [Writing Patterns](writing-patterns.md) — create custom review patterns
- [CLI Reference](cli.md) — all commands and flags
- [LLM Providers](llm-providers.md) — provider-specific setup
