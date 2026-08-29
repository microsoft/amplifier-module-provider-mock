# Amplifier Mock Provider Module

> **Note**: This is a **reference provider module** for Amplifier. It demonstrates how to implement a provider and is useful for testing and development without API calls.

## Prerequisites

- **Python 3.11+**
- **[UV](https://github.com/astral-sh/uv)** - Fast Python package manager

### Installing UV

```bash
# macOS/Linux/WSL
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Purpose

Provides pre-configured responses for testing and development without calling real LLM APIs.

## Contract

**Module Type:** Provider
**Mount Point:** `providers`
**Entry Point:** `amplifier_module_provider_mock:mount`

## Configuration

```yaml
providers:
  - module: provider-mock
    name: mock
    config:
      responses:
        - "Response 1"
        - "Response 2"
        - "Response 3"
      debug: false             # Enable raw event emission (see below)
      use_streaming: true      # Emit llm:stream_* events (default: true)
      stream_delay_ms: 0       # Delay between streamed word fragments (ms)
```

### All config keys

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `responses` | list | 3 canned strings | Rotated on each call: call N returns `responses[(N-1) % len(responses)]`. Each entry is either a plain string (single text block) or a dict `{"thinking": "...", "text": "..."}` (emits a thinking block at index 0, then a text block at index 1 -- matches the Anthropic extended-thinking contract shape). |
| `debug` | bool | `false` | Enables raw event emission (see below) |
| `raw_debug` | bool | `false` | Accepted alias for `debug` (deprecated -- setting `raw_debug` without `debug` now still enables raw events, with a warning suggesting `debug` directly) |
| `use_streaming` | bool | `true` | Set `false` to force the non-streaming path (only `llm:request`/`llm:response`, no `llm:stream_*` events) |
| `stream_delay_ms` | int | `0` | Delay in milliseconds between each streamed word fragment -- useful for visually inspecting streaming UIs |

Boolean keys accept native `true`/`false` or the string forms a config
wizard writes (`"true"`/`"false"`). Unrecognized config keys produce a
mount-time warning with a did-you-mean suggestion (e.g. a stray `delay`
key suggests `stream_delay_ms`).

This provider has no `ConfigField` wizard prompts and no
`extra_request_params` -- it makes no real request to merge arbitrary
params into.

### Debug events

Setting `debug: true` emits `llm:request:raw` and `llm:response:raw` --
containing the complete mock request/response objects (message counts,
tool-call info, usage). There is no separate `llm:request:debug`/
`llm:response:debug` "standard debug" tier in this provider (documented in
older versions of this README, but never implemented) -- `debug` is a
single on/off switch for the raw events.

**Example**:
```yaml
providers:
  - module: provider-mock
    config:
      debug: true      # Enable raw event capture
      responses: ["Test response 1", "Test response 2"]
```

## Behavior

- Returns responses from the configured list in rotation (call 1 ->
  `responses[0]`, call 2 -> `responses[1]`, ...)
- Can simulate tool calls when prompt contains "read"
- No external API calls
- No authentication required

## Dependencies

- `amplifier-core>=1.0.0`

## Contributing

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
