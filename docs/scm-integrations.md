# SCM Integrations

CodeSentinel integrates with multiple source control platforms for fetching PR diffs and posting review comments.

## GitHub

### Setup

```bash
export GITHUB_TOKEN=ghp_...
```

The token needs `repo` scope for private repositories, or `public_repo` for public ones.

### Usage

```bash
# Review a PR
codesentinel review --pr https://github.com/org/repo/pull/123

# Enable PR comments in config
```

```yaml
reporters:
  github:
    enabled: true
    post_review: true
    request_changes_on: "critical"
    comment_style: "both"          # inline | summary | both
```

### PR Identifier Formats

- Full URL: `https://github.com/owner/repo/pull/123`
- Short: `owner/repo#123`

## GitLab

### Setup

```bash
export GITLAB_TOKEN=glpat-...
```

The token needs `api` scope.

### Usage

```bash
codesentinel review --pr https://gitlab.com/group/project/-/merge_requests/42
```

```yaml
reporters:
  gitlab:
    enabled: true
    post_review: true
    request_changes_on: "critical"
    comment_style: "both"
```

### MR Identifier Formats

- Full URL: `https://gitlab.com/group/project/-/merge_requests/42`
- Short: `group/project!42`

### Custom Instance

```yaml
# For self-hosted GitLab
# Set base_url via the GitLabSCM constructor
```

## Azure DevOps

### Setup

```bash
export AZURE_DEVOPS_TOKEN=your-personal-access-token
```

The PAT needs `Code (Read & Write)` scope.

### Usage

```bash
codesentinel review --pr https://dev.azure.com/org/project/_git/repo/pullrequest/123
```

```yaml
reporters:
  azure_devops:
    enabled: true
    post_review: true
    request_changes_on: "critical"
    comment_style: "both"
```

### PR Identifier Formats

- Full URL: `https://dev.azure.com/org/project/_git/repo/pullrequest/123`
- Legacy URL: `https://org.visualstudio.com/project/_git/repo/pullrequest/123`
- Short: `org/project/repo#123`

## Bitbucket

### Setup

```bash
export BITBUCKET_TOKEN=your-token
```

For app passwords, also set `BITBUCKET_USERNAME`.

### Usage

```bash
codesentinel review --pr https://bitbucket.org/workspace/repo/pull-requests/42
```

### PR Identifier Formats

- Full URL: `https://bitbucket.org/workspace/repo/pull-requests/42`
- Short: `workspace/repo#42`

## Local Git

For reviewing local branches and staged changes without any API calls.

### Usage

```bash
# Review a branch
codesentinel review --branch feature/my-feature --base main --repo .

# Review staged changes
codesentinel review --staged --repo .
```

No token or configuration needed for local Git operations.

## Comment Styles

All PR-based reporters support three comment styles:

| Style | Behavior |
|-------|----------|
| `inline` | Post comments on specific file/line locations |
| `summary` | Post a single summary comment on the PR |
| `both` | Post both inline and summary comments (default) |

## Request Changes Behavior

When `request_changes_on` is set, findings at or above that severity trigger a "request changes" action on the PR:

```yaml
reporters:
  github:
    request_changes_on: "high"   # Request changes on HIGH or CRITICAL
```

If no findings reach the threshold, the review is posted as a comment only. If there are zero findings, the PR is approved.
