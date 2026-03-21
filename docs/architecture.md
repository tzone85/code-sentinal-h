# Architecture

CodeSentinel follows a pipeline architecture where each stage transforms data and passes it to the next. All core data structures are frozen (immutable) dataclasses.

## Component Overview

```
src/codesentinel/
├── cli/              # Entry point — Typer CLI application
├── config/           # 3-tier configuration loading and validation
├── core/             # Pipeline orchestration and data transformation
│   ├── engine.py     # ReviewEngine — main orchestrator
│   ├── diff_parser.py
│   ├── file_classifier.py
│   ├── pattern_matcher.py
│   ├── context_builder.py
│   ├── post_processor.py
│   └── prompts.py
├── llm/              # LLM provider abstraction (Claude, OpenAI, Ollama)
├── patterns/         # Pattern schema, loading, validation, registry
├── reporters/        # Output formatting (terminal, JSON, SARIF, PR comments)
└── scm/              # Source control integrations (GitHub, GitLab, etc.)
```

## Review Pipeline

The `ReviewEngine` in `core/engine.py` orchestrates the full review flow:

```
┌─────────────────┐
│  CLI / Action    │  User invokes `codesentinel review`
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Config Loader   │  Merge: defaults → user config → repo config
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Diff Extraction │  From file, branch, PR, or staged changes
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Diff Parser     │  Regex-based unified diff → FileDiff[]
└────────┬────────┘  Extracts: files, hunks, added/removed lines
         │
         ▼
┌─────────────────┐
│ File Classifier  │  Enriches each file with:
└────────┬────────┘  language, file_type, module, layer, framework_hints
         │
         ▼
┌─────────────────┐
│ Pattern Matcher  │  For each file, find applicable patterns using:
└────────┬────────┘  glob match + exclusion + language compatibility
         │
         ▼
┌─────────────────┐
│ Context Builder  │  Group files by module, build ReviewChunk[]
└────────┬────────┘  Respects LLM token budget, deduplicates patterns
         │
         ▼
┌─────────────────┐
│  LLM Review      │  Parallel async calls to LLM provider
│  (concurrent)    │  System prompt + user prompt (diff + patterns)
└────────┬────────┘  Returns: raw JSON findings per chunk
         │
         ▼
┌─────────────────┐
│ Post Processor   │  Parse JSON → Finding[]
└────────┬────────┘  Deduplicate (rapidfuzz >0.85 similarity)
         │           Filter by severity and confidence
         │           Sort by severity (critical first)
         │           Truncate to max_findings
         ▼
┌─────────────────┐
│   Reporters      │  Terminal, JSON, SARIF, PR comments
└─────────────────┘  Each reporter independently formats results
```

## Stage Details

### 1. Diff Parser (`core/diff_parser.py`)

Parses unified diff format using regex. Handles Git extended headers (mode changes, renames, binary files, similarity index). Produces `ParsedDiff` containing `FileDiff[]` with hunks and line-level detail.

### 2. File Classifier (`core/file_classifier.py`)

Enriches `FileDiff` objects with metadata:
- **Language** — detected from file extension via `LANGUAGE_MAP` (50+ extensions)
- **File type** — `SOURCE`, `TEST`, `CONFIG`, `MIGRATION`, `DOCS`, `CI`
- **Module** — inferred from directory structure
- **Layer** — `controller`, `service`, `repository`, `model`, etc.
- **Framework hints** — detected from file paths and names

### 3. Pattern Matcher (`core/pattern_matcher.py`)

Matches classified files against loaded patterns. A pattern applies to a file when ALL of:
1. File path matches at least one `applies_to.include` glob
2. File path does NOT match any `applies_to.exclude` glob
3. Pattern language is `null` (language-agnostic) or matches file language

### 4. Context Builder (`core/context_builder.py`)

Groups matched files by module, deduplicates patterns per group, and splits into `ReviewChunk[]` that fit within the LLM's token budget. Token estimation uses ~4 characters per token with ~2,000 tokens overhead per chunk.

### 5. LLM Review

Sends chunks in parallel using `asyncio.gather()`. Concurrency is controlled by `max_concurrent_requests` (default: 3). Each chunk gets a system prompt (containing review mode, confidence threshold, pattern definitions) and a user prompt (containing the diff). Retries once on failure with a 1-second delay.

### 6. Post Processor (`core/post_processor.py`)

Parses raw LLM JSON responses into `Finding` objects, then:
1. **Deduplicates** — removes near-duplicate findings (rapidfuzz similarity >0.85)
2. **Filters** — removes findings below `min_severity` and `min_confidence`
3. **Sorts** — critical findings first
4. **Truncates** — limits to `max_findings`

### 7. Reporters

Each reporter independently formats `ReviewResult`:
- **Terminal** — Rich console with color-coded severity
- **JSON** — Pretty-printed JSON file
- **SARIF** — SARIF v2.1 for IDE/GitHub code scanning
- **PR comments** — Inline + summary comments on GitHub/GitLab/Azure DevOps/Bitbucket

## Key Data Models

All models are frozen (immutable) to prevent hidden side effects:

| Model | Location | Purpose |
|-------|----------|---------|
| `FileDiff` | `core/models.py` | Parsed diff for a single file |
| `ClassifiedFile` | `core/models.py` | File with language/type/layer metadata |
| `Pattern` | `patterns/schema.py` | Pattern definition from YAML |
| `ReviewChunk` | `core/models.py` | Files + patterns ready for LLM |
| `Finding` | `core/models.py` | Single review finding |
| `ReviewResult` | `core/models.py` | Complete review output |
| `ReviewStats` | `core/models.py` | Aggregated statistics |
| `PRInfo` | `core/models.py` | PR metadata from SCM |
| `LLMResponse` | `core/models.py` | LLM call result |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No findings at or above the `fail_on` severity |
| 1 | Findings found at or above the `fail_on` severity |
| 2 | Invalid arguments or configuration |
| 3 | Runtime error (LLM failure, SCM error, etc.) |

## Severity Model

Severities are ordered and comparable:

```
CRITICAL (5) > HIGH (4) > MEDIUM (3) > LOW (2) > INFO (1)
```

The `fail_on` severity in config determines which findings cause a non-zero exit code. In `gatekeeping` mode, critical and high findings trigger `request_changes` on PRs.
