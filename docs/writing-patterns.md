# Writing Custom Patterns

Patterns are YAML files that tell CodeSentinel what to look for during code review. Each pattern defines detection signals, examples, and remediation guidance that the LLM uses to identify violations.

## Pattern File Structure

```yaml
apiVersion: v1
kind: Pattern
metadata:
  name: "my-pattern-name"
  category: "security"
  language: "python"
  severity: "high"
  tags: ["security", "input-validation"]
  confidence_threshold: 0.7

spec:
  description: >
    What this pattern checks for.

  rationale: >
    Why this pattern matters.

  applies_to:
    include:
      - "**/*.py"
    exclude:
      - "**/test/**"

  detection:
    positive_signals:
      - "Signal that indicates a violation"
    negative_signals:
      - "Signal that indicates compliance"
    context_clues:
      - "Additional context for the LLM"

  examples:
    correct:
      - description: "Good example"
        code: |
          # correct code
    incorrect:
      - description: "Bad example"
        code: |
          # incorrect code

  remediation: >
    How to fix violations.

  references:
    - title: "Reference Name"
      url: "https://example.com"
```

## Schema Reference

### `metadata` (required)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unique kebab-case identifier (e.g., `security-no-hardcoded-secrets`) |
| `category` | string | yes | Grouping category (e.g., `security`, `architecture`, `testing`) |
| `language` | string | no | Target language (`python`, `java`, `typescript`, etc.). Omit or set `null` for language-agnostic patterns |
| `severity` | string | yes | Default severity: `critical`, `high`, `medium`, `low`, or `info` |
| `tags` | list | no | Searchable tags for filtering |
| `confidence_threshold` | float | no | Minimum confidence (0.0–1.0) for findings from this pattern. Default: 0.7 |

### `spec.applies_to` (required)

| Field | Type | Description |
|-------|------|-------------|
| `include` | list of globs | File paths where this pattern applies. At least one must match. |
| `exclude` | list of globs | File paths where this pattern does NOT apply. Any match excludes the file. |

Glob patterns use `fnmatch` syntax. Use `**/` prefix to match any directory depth.

### `spec.detection` (required)

| Field | Type | Description |
|-------|------|-------------|
| `positive_signals` | list | Indicators that suggest a violation exists. The LLM looks for these. |
| `negative_signals` | list | Indicators that suggest compliance. The LLM treats these as "not a violation." |
| `context_clues` | list | Additional context to help the LLM make better decisions. |

### `spec.examples` (recommended)

Provide `correct` and `incorrect` examples. Each has a `description` and `code` block. Examples significantly improve LLM detection accuracy.

### `spec.remediation` (required)

A clear, actionable description of how to fix violations. This is shown to the developer in findings.

### `spec.references` (optional)

Links to documentation, standards, or guidelines. Each entry has `title` and `url`.

## Pattern Loading

Patterns are loaded from three sources, in order:

1. **Built-in** — 16 patterns shipped with CodeSentinel
2. **Remote** — Git repositories (cloned and cached)
3. **Local** — YAML files in your project

If two patterns share the same `name`, the later source wins.

### Local patterns

Place `.yaml` files in `.codesentinel/patterns/` or configure paths in your config:

```yaml
patterns:
  local:
    - ".codesentinel/patterns/"
    - "/shared/team-patterns/"
```

### Remote patterns

Reference Git repositories in your config:

```yaml
patterns:
  remote:
    - repo: "https://github.com/org/patterns.git"
      path: "patterns/"
      ref: "main"
      cache_ttl: 3600
```

### Disabling built-in patterns

```yaml
patterns:
  builtin:
    enabled: false
```

Or selectively exclude:

```yaml
patterns:
  builtin:
    exclude:
      - "spring-boot-layers"
      - "ddd-aggregates"
```

## Pattern Matching Rules

A pattern applies to a file when ALL of these are true:

1. The file path matches at least one `applies_to.include` glob
2. The file path does NOT match any `applies_to.exclude` glob
3. The pattern's `language` is `null` OR matches the file's detected language

## Tips for Effective Patterns

**Be specific with signals.** Vague signals like "bad code" produce low-confidence findings. Instead, describe concrete indicators: "function accepts raw SQL string as parameter."

**Provide both positive and negative signals.** Negative signals prevent false positives. For example, a "hardcoded secrets" pattern should have a negative signal for "value loaded from environment variable."

**Include code examples.** The LLM uses examples to calibrate its detection. Two good examples (one correct, one incorrect) are more valuable than five vague signals.

**Use appropriate severity.** Reserve `critical` for security vulnerabilities and data loss risks. Use `medium` for style and convention violations.

**Scope with globs.** Narrow `applies_to.include` patterns reduce noise. A Spring Boot pattern should only match `**/*.java`, not all files.

**Test your patterns.** Use `codesentinel patterns validate my-pattern.yaml` to check syntax, then run against known-violating diffs to verify detection.

## Example: Custom Pattern

```yaml
apiVersion: v1
kind: Pattern
metadata:
  name: "no-print-statements"
  category: "code-quality"
  language: "python"
  severity: "low"
  tags: ["debugging", "cleanup"]

spec:
  description: >
    Detects print() statements that should be replaced with proper logging.

  rationale: >
    Print statements bypass the logging framework, cannot be filtered by level,
    and may leak sensitive data to stdout in production.

  applies_to:
    include:
      - "**/*.py"
    exclude:
      - "**/test/**"
      - "**/scripts/**"
      - "manage.py"

  detection:
    positive_signals:
      - "print() call in application code"
      - "f-string or format string passed to print()"
    negative_signals:
      - "print() inside a CLI command handler"
      - "print() in a script meant for local execution"
    context_clues:
      - "check if the file is part of a web application or library"

  examples:
    correct:
      - description: "Using the logging module"
        code: |
          import logging
          logger = logging.getLogger(__name__)
          logger.info("Processing request for user %s", user_id)
    incorrect:
      - description: "Using print for debugging"
        code: |
          print(f"Processing request for user {user_id}")

  remediation: >
    Replace print() with the appropriate logging call:
    logger.debug() for debugging, logger.info() for operational messages,
    logger.warning() for unexpected situations.

  references:
    - title: "Python Logging HOWTO"
      url: "https://docs.python.org/3/howto/logging.html"
```

## Built-in Pattern Inventory

CodeSentinel ships with 16 patterns across four categories:

### General (language-agnostic)
- `api-design` — API contracts and response envelopes
- `error-handling` — Error propagation and user-friendly messages
- `naming-conventions` — Consistent naming across the codebase
- `security-basics` — Input validation, output encoding
- `security-no-hardcoded-secrets` — No hardcoded API keys, passwords, or tokens
- `testing-patterns` — Test coverage, isolation, naming

### Java
- `clean-architecture` — Dependency inversion, layer separation
- `ddd-aggregates` — Domain-driven design aggregate patterns
- `event-driven` — Event sourcing and async message patterns
- `spring-boot-layers` — Spring Boot layer structure and bean management

### Python
- `django-patterns` — Django MTV conventions, queryset optimization
- `fastapi-patterns` — FastAPI route organization, dependency injection
- `pep8-beyond-linting` — Code structure beyond PEP 8

### TypeScript
- `nestjs-patterns` — NestJS module/controller/service structure
- `nextjs-patterns` — Next.js page organization, API routes
- `react-patterns` — React component design, hooks usage
