# Changelog

All notable changes to CodeSentinel will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Core review pipeline: DiffParser, FileClassifier, PatternMatcher, ContextBuilder, PostProcessor
- ReviewEngine orchestrator with parallel async LLM calls
- 3-tier configuration system with deep merge (defaults → user → repo)
- LLM providers: Claude (Anthropic), OpenAI, Ollama
- SCM providers: GitHub, GitLab, Azure DevOps, Bitbucket, Local Git
- Reporters: Terminal (Rich), JSON, SARIF, GitHub PR, GitLab MR, Azure DevOps PR, Bitbucket PR
- 16 built-in patterns across Java, Python, TypeScript, and general categories
- Pattern system with YAML schema, validation, and registry
- CLI with review, patterns, config, and init commands
- Rate limiter with semaphore-based concurrency control
- Custom pattern support (local and remote Git repositories)
- Exit code system (0: clean, 1: findings, 2: config error, 3: runtime error)
- Comprehensive documentation suite
