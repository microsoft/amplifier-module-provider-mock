"""
Mock provider module for testing.
Returns pre-configured responses without calling real APIs.
"""

# Amplifier module metadata
__amplifier_module_type__ = "provider"

import logging
from typing import Any

from amplifier_core import ModelInfo
from amplifier_core import ModuleCoordinator
from amplifier_core import ProviderInfo
from amplifier_core.message_models import ChatRequest
from amplifier_core.message_models import ChatResponse
from amplifier_core.message_models import TextBlock
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
    """Mock provider for testing without API calls."""

    name = "mock"

    def __init__(
        self, config: dict[str, Any], coordinator: ModuleCoordinator | None = None
    ):
        self.responses = config.get(
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

    def get_info(self) -> ProviderInfo:
        """Get provider metadata."""
        return ProviderInfo(
            id="mock",
            display_name="Mock Provider",
            credential_env_vars=[],  # No credentials needed
            capabilities=["tools", "testing"],
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
                capabilities=["tools", "testing"],
                defaults={"temperature": 0.7, "max_tokens": 4096},
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
                metadata={"cost_tier": "free"},
            ),
        ]

    async def complete(self, request: ChatRequest, **kwargs) -> ChatResponse:
        """Generate a mock completion from ChatRequest."""
        self.call_count += 1

        # RAW DEBUG: Complete mock request (ultra-verbose)
        if (
            self.coordinator
            and hasattr(self.coordinator, "hooks")
            and self.debug
            and self.raw_debug
        ):
            await self.coordinator.hooks.emit(
                "llm:request:raw",
                {
                    "lvl": "DEBUG",
                    "provider": "mock",
                    "message_count": len(request.messages),
                    "call_count": self.call_count,
                },
            )

        # Check last message content for simple pattern matching
        last_message = request.messages[-1] if request.messages else None
        content = ""
        if last_message and isinstance(last_message.content, str):
            content = last_message.content
        elif last_message and isinstance(last_message.content, list):
            # Extract text from TextBlock only
            for block in last_message.content:
                if block.type == "text":
                    content = block.text
                    break

        # Simple pattern matching for tool calls
        tool_calls = []
        if "read" in content.lower():
            tool_calls.append(
                ToolCall(id="mock_tool_1", name="read", arguments={"path": "test.txt"})
            )

        # Generate response
        if tool_calls:
            # Response with tool calls
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
            # Regular text response
            response_text = self.responses[self.call_count % len(self.responses)]
            response = ChatResponse(
                content=[TextBlock(text=response_text)],
                usage=Usage(
                    input_tokens=10,
                    output_tokens=20,
                    total_tokens=30,
                    reasoning_tokens=None,
                    cache_read_tokens=None,
                    cache_write_tokens=None,
                ),
            )

        # RAW DEBUG: Complete mock response (ultra-verbose)
        if (
            self.coordinator
            and hasattr(self.coordinator, "hooks")
            and self.debug
            and self.raw_debug
        ):
            await self.coordinator.hooks.emit(
                "llm:response:raw",
                {
                    "lvl": "DEBUG",
                    "provider": "mock",
                    "has_tool_calls": bool(tool_calls),
                    "tool_count": len(tool_calls),
                },
            )

        return response

    def parse_tool_calls(self, response: ChatResponse) -> list[ToolCall]:
        """Parse tool calls from ChatResponse."""
        return response.tool_calls or []
