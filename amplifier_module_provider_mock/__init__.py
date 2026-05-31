"""
Mock provider module for testing.
Returns pre-configured responses without calling real APIs.

Implements the provider streaming contract: synthetic token streaming
from canned responses, making this the deterministic conformance fixture
for the streaming event sequence.
"""

# Amplifier module metadata
__amplifier_module_type__ = "provider"

import asyncio
import logging
import uuid
from typing import Any

from amplifier_core import ModelInfo
from amplifier_core import ModuleCoordinator
from amplifier_core import ProviderInfo
from amplifier_core.message_models import ChatRequest
from amplifier_core.message_models import ChatResponse
from amplifier_core.message_models import TextBlock
from amplifier_core.message_models import ThinkingBlock
from amplifier_core.message_models import ToolCall
from amplifier_core.message_models import Usage

logger = logging.getLogger(__name__)


async def mount(coordinator: ModuleCoordinator, config: dict[str, Any] | None = None):
    """Mount the mock provider."""
    config = config or {}
    provider = MockProvider(config, coordinator)
    await coordinator.mount("providers", provider, name="mock")
    logger.info("Mounted MockProvider")
    return


class MockProvider:
    """Mock provider for testing without API calls.

    Implements the provider streaming contract by synthesising a token
    stream from canned response strings.  This makes it the canonical
    deterministic fixture: tests can assert exact event names, payload
    keys, sequence numbers, and request_id consistency without any
    external dependencies.

    Response entries in ``config["responses"]`` may be:
    - A plain string  -> emits a single text block.
    - A dict ``{"thinking": "...", "text": "..."}``
      -> emits a thinking block (block_index 0) followed by a text block
         (block_index 1), exactly matching the Anthropic extended-thinking
         contract shape.
    """

    name = "mock"
    use_streaming: bool

    def __init__(
        self, config: dict[str, Any], coordinator: ModuleCoordinator | None = None
    ):
        self.responses: list[Any] = config.get(
            "responses",
            [
                "I'll help you with that task.",
                "Task completed successfully.",
                "Here's the result of your request.",
            ],
        )
        self.call_count = 0
        self.coordinator = coordinator
        self.debug = config.get("debug", False)
        self.raw_debug = config.get("raw_debug", False)
        # Streaming defaults — mirrors the contract's per-provider class default.
        self.use_streaming = config.get("use_streaming", True)
        self._config = config  # retained for stream_delay_ms

    def get_info(self) -> ProviderInfo:
        """Get provider metadata."""
        return ProviderInfo(
            id="mock",
            display_name="Mock Provider",
            credential_env_vars=[],  # No credentials needed
            capabilities=["tools", "testing", "streaming"],
            defaults={
                "model": "mock-model",
                "max_tokens": 4096,
                "temperature": 0.7,
            },
        )

    async def list_models(self) -> list[ModelInfo]:
        """List available mock models."""
        return [
            ModelInfo(
                id="mock-model",
                display_name="Mock Model",
                context_window=100000,
                max_output_tokens=4096,
                capabilities=["tools", "testing", "streaming"],
                defaults={"temperature": 0.7, "max_tokens": 4096},
            ),
        ]

    async def complete(self, request: ChatRequest, **kwargs) -> ChatResponse:
        """Generate a mock completion from ChatRequest.

        Streaming path (default, use_streaming=True):
          Emits per the provider streaming contract:
            llm:request
            llm:stream_block_start  (block_type "thinking", index 0, if thinking dict)
            llm:stream_block_delta(block_type="thinking")  x N  (if thinking dict)
            llm:stream_block_end  (thinking block, if present)
            llm:stream_block_start  (block_type "text")
            llm:stream_block_delta  x M  (one per whitespace-separated word + " ")
            llm:stream_block_end  (text block)
            llm:response

        Non-streaming path (use_streaming=False or metadata stream=False):
          Emits only llm:request and llm:response — no llm:stream_* events.
        """
        self.call_count += 1

        # Resolve hooks once: use a local alias so every emit call through
        # it is type-safe (no repeated Optional dereference).
        _hooks = (
            self.coordinator.hooks
            if self.coordinator and hasattr(self.coordinator, "hooks")
            else None
        )

        # --- RAW DEBUG (ultra-verbose, gated) ---
        if _hooks and self.debug and self.raw_debug:
            await _hooks.emit(
                "llm:request:raw",
                {
                    "lvl": "DEBUG",
                    "provider": "mock",
                    "message_count": len(request.messages),
                    "call_count": self.call_count,
                },
            )

        # --- Standard llm:request (always when hooks available) ---
        if _hooks:
            await _hooks.emit(
                "llm:request",
                {
                    "provider": "mock",
                    "model": (getattr(request, "model", None) or "mock-model"),
                    "message_count": len(request.messages),
                },
            )

        # --- Per-call streaming override (contract §Per-request stream override) ---
        # The override is LOCAL — it must NOT mutate self.use_streaming.
        _use_streaming = self.use_streaming
        _meta = getattr(request, "metadata", None)
        if isinstance(_meta, dict) and _meta.get("stream") is False:
            _use_streaming = False

        # --- Extract last-message content for pattern matching ---
        last_message = request.messages[-1] if request.messages else None
        content = ""
        if last_message and isinstance(last_message.content, str):
            content = last_message.content
        elif last_message and isinstance(last_message.content, list):
            for block in last_message.content:
                if block.type == "text":
                    content = block.text
                    break

        # --- Tool-call path ---
        tool_calls = []
        if "read" in content.lower():
            tool_calls.append(
                ToolCall(id="mock_tool_1", name="read", arguments={"path": "test.txt"})
            )

        # --- Build response ---
        if tool_calls:
            # Tool calls: no streaming per contract (§tool_use blocks).
            response = ChatResponse(
                content=[TextBlock(text="I'll read that file for you.")],
                tool_calls=tool_calls,
                usage=Usage(
                    input_tokens=10,
                    output_tokens=5,
                    total_tokens=15,
                    reasoning_tokens=None,
                    cache_read_tokens=None,
                    cache_write_tokens=None,
                ),
            )
        else:
            # --- Text (or thinking+text) path ---
            response_entry = self.responses[self.call_count % len(self.responses)]
            is_thinking = (
                isinstance(response_entry, dict) and "thinking" in response_entry
            )

            # Initialise to placate type checkers; each branch below always sets both.
            text: str = ""
            thinking_text: str = ""
            response_content: list[Any]
            if is_thinking:
                thinking_text = str(response_entry["thinking"])
                text = str(response_entry["text"])
                response_content = [
                    ThinkingBlock(thinking=thinking_text),
                    TextBlock(text=text),
                ]
            else:
                text = str(response_entry)
                response_content = [TextBlock(text=text)]

            usage = Usage(
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                reasoning_tokens=None,
                cache_read_tokens=None,
                cache_write_tokens=None,
            )
            response = ChatResponse(content=response_content, usage=usage)

            # --- Streaming path ---
            if _use_streaming and _hooks:
                request_id = str(uuid.uuid4())
                stream_delay = self._config.get("stream_delay_ms", 0) / 1000.0
                partial_emitted = False

                try:
                    block_index = 0

                    # Thinking block (optional)
                    if is_thinking:
                        await _hooks.emit(
                            "llm:stream_block_start",
                            {
                                "request_id": request_id,
                                "block_index": block_index,
                                "block_type": "thinking",
                            },
                        )
                        for seq, word in enumerate(thinking_text.split()):
                            fragment = word + " "
                            if fragment:  # guard: never emit empty
                                await _hooks.emit(
                                    "llm:stream_block_delta",
                                    {
                                        "request_id": request_id,
                                        "block_index": block_index,
                                        "block_type": "thinking",
                                        "sequence": seq,
                                        "text": fragment,
                                    },
                                )
                                partial_emitted = True
                                await asyncio.sleep(stream_delay)
                        await _hooks.emit(
                            "llm:stream_block_end",
                            {
                                "request_id": request_id,
                                "block_index": block_index,
                                "block_type": "thinking",
                            },
                        )
                        block_index += 1

                    # Text block
                    await _hooks.emit(
                        "llm:stream_block_start",
                        {
                            "request_id": request_id,
                            "block_index": block_index,
                            "block_type": "text",
                        },
                    )
                    for seq, word in enumerate(text.split()):
                        fragment = word + " "
                        if fragment:  # guard: never emit empty
                            await _hooks.emit(
                                "llm:stream_block_delta",
                                {
                                    "request_id": request_id,
                                    "block_index": block_index,
                                    "block_type": "text",
                                    "sequence": seq,
                                    "text": fragment,
                                },
                            )
                            partial_emitted = True
                            await asyncio.sleep(stream_delay)
                    await _hooks.emit(
                        "llm:stream_block_end",
                        {
                            "request_id": request_id,
                            "block_index": block_index,
                            "block_type": "text",
                        },
                    )

                except Exception as exc:
                    if partial_emitted:
                        await _hooks.emit(
                            "llm:stream_aborted",
                            {
                                "request_id": request_id,
                                "error": {
                                    "type": type(exc).__name__,
                                    "msg": str(exc),
                                },
                            },
                        )
                    raise

        # --- RAW DEBUG response (ultra-verbose, gated) ---
        if _hooks and self.debug and self.raw_debug:
            await _hooks.emit(
                "llm:response:raw",
                {
                    "lvl": "DEBUG",
                    "provider": "mock",
                    "has_tool_calls": bool(tool_calls),
                    "tool_count": len(tool_calls),
                },
            )

        # --- Standard llm:response (always when hooks available) ---
        if _hooks:
            model = getattr(request, "model", None) or "mock-model"
            _usage = response.usage
            await _hooks.emit(
                "llm:response",
                {
                    "provider": "mock",
                    "model": model,
                    "status": "ok",
                    "usage": {
                        "input_tokens": _usage.input_tokens if _usage else 0,
                        "output_tokens": _usage.output_tokens if _usage else 0,
                        "total_tokens": _usage.total_tokens if _usage else 0,
                    },
                },
            )

        return response

    def parse_tool_calls(self, response: ChatResponse) -> list[ToolCall]:
        """Parse tool calls from ChatResponse."""
        return response.tool_calls or []
