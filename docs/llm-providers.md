# LLM Providers

CodeSentinel supports three LLM providers. Each requires different setup.

## Claude (Anthropic) — Recommended

The default provider. Uses Claude's system prompt support and JSON response formatting for high-quality review findings.

### Setup

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Config

```yaml
llm:
  provider: "claude"
  model: "claude-sonnet-4-20250514"   # Default model
  max_tokens: 4096
  temperature: 0.2
```

### Supported Models

Any model available via the Anthropic API. Common choices:
- `claude-sonnet-4-20250514` — best balance of quality and speed (default)
- `claude-opus-4-20250514` — deepest reasoning for complex reviews

### Token Estimation

Claude uses ~3 characters per token for estimation.

### Context Window

Up to 200,000 tokens depending on model.

## OpenAI

Uses the OpenAI chat completions API with JSON mode.

### Setup

```bash
export OPENAI_API_KEY=sk-...
```

### Config

```yaml
llm:
  provider: "openai"
  model: "gpt-4o"               # Default for OpenAI
  max_tokens: 4096
  temperature: 0.2
```

### Supported Models

Any model available via the OpenAI API. Common choices:
- `gpt-4o` — fast and capable (default)
- `gpt-4-turbo` — larger context window

### Context Window

Up to 128,000 tokens for GPT-4o.

## Ollama (Local)

Run reviews locally without sending code to external APIs. Requires Ollama running on your machine.

### Setup

```bash
# Install Ollama (macOS)
brew install ollama

# Start the server
ollama serve

# Pull a model
ollama pull llama3
```

No API key needed.

### Config

```yaml
llm:
  provider: "ollama"
  model: "llama3"               # Default for Ollama
  ollama:
    endpoint: "http://localhost:11434"  # Default endpoint
```

### Considerations

- Runs entirely locally — no code leaves your machine
- Quality depends on the model; larger models produce better reviews
- Slower than cloud providers on most hardware

## Provider Interface

All providers implement the same interface:

```python
async def review(system_prompt, user_prompt, response_format) -> LLMResponse
def estimate_tokens(text) -> int
def max_context_tokens() -> int
```

This means switching providers requires only a config change — no code modifications.

## Concurrency

All providers support concurrent requests controlled by `max_concurrent_requests` (default: 3). The rate limiter uses an async semaphore to prevent overwhelming the API. Failed requests are retried once after a 1-second delay.

```yaml
llm:
  max_concurrent_requests: 5    # Increase for faster reviews of large diffs
```
