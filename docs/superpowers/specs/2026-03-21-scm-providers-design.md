# SCM Providers Design — STORY-CS-018

## Summary

Implement the source control management abstraction layer and two initial providers (GitHub, Local Git) following the established Provider Pattern used by LLM providers and Reporters.

## Architecture

### Files

| File | Purpose |
|------|---------|
| `src/codesentinel/scm/base.py` | Abstract `SCMProvider` base class |
| `src/codesentinel/scm/github.py` | `GitHubSCM` — GitHub API integration via httpx |
| `src/codesentinel/scm/local_git.py` | `LocalGitSCM` — local git operations via gitpython |
| `src/codesentinel/scm/__init__.py` | Re-exports for public API |
| `tests/unit/test_scm_base.py` | Tests for base class contract |
| `tests/unit/test_scm_github.py` | Tests for GitHub provider |
| `tests/unit/test_scm_local_git.py` | Tests for Local Git provider |

### Abstract Base: `SCMProvider`

Five async abstract methods matching the story specification:

```python
class SCMProvider(ABC):
    async def get_pr_info(self, pr_identifier: str) -> PRInfo
    async def get_pr_diff(self, pr_identifier: str) -> str
    async def post_review_comment(self, pr_identifier: str, file_path: str, line: int, body: str, severity: str) -> None
    async def post_review_summary(self, pr_identifier: str, body: str, approve: bool, request_changes: bool) -> None
    async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str
```

### GitHub Provider: `GitHubSCM`

- **Auth**: Token-based via `Authorization: Bearer <token>` header
- **HTTP client**: `httpx.AsyncClient` (consistent with project's async patterns)
- **PR identifier parsing**: Supports both `owner/repo#123` and full GitHub URL formats
- **Diff fetching**: Uses `Accept: application/vnd.github.diff` header
- **Review comments**: Creates PR review comments via GitHub Reviews API (inline on specific files/lines)
- **Review summary**: Submits PR review with APPROVE, REQUEST_CHANGES, or COMMENT event
- **`get_local_diff`**: Raises `NotImplementedError` — not applicable for remote SCM
- **Error handling**: All httpx errors caught and re-raised as `SCMError`
- **Enterprise support**: Optional `base_url` parameter (defaults to `https://api.github.com`)

### Local Git Provider: `LocalGitSCM`

- **Library**: `gitpython` (`git.Repo`)
- **`get_local_diff`**: Runs `git diff base_branch..head_branch` between branches
- **Staged support**: When `head_branch` is `"--staged"` or `"--cached"`, uses `git diff --cached`
- **Remote methods**: `get_pr_info`, `get_pr_diff`, `post_review_comment`, `post_review_summary` all raise `NotImplementedError`
- **Error handling**: Git errors caught and re-raised as `SCMError`

## Design Decisions

1. **Follows Provider Pattern**: Mirrors `llm/base.py` → `llm/claude.py` structure exactly
2. **Frozen data models**: Uses existing `PRInfo` frozen dataclass (already defined in `core/models.py`)
3. **SCMError**: Uses existing exception from `core/exceptions.py`
4. **Async throughout**: All methods are async even for gitpython (consistency with the interface)
5. **No factory**: Engine already handles provider selection; adding a factory would be premature

## Error Handling

- All external calls (httpx, gitpython) wrapped in try/except
- Re-raised as `SCMError` with descriptive messages
- HTTP 4xx/5xx responses checked explicitly with status codes in error messages
- Invalid PR identifiers raise `SCMError` immediately (fail fast)

## Testing Strategy

- **Unit tests**: Mock `httpx.AsyncClient` responses and `git.Repo` operations
- **PR identifier parsing**: Test both URL and `owner/repo#number` formats, plus invalid inputs
- **Error paths**: Test network errors, invalid responses, git errors
- **Coverage target**: 80%+ for all SCM modules
