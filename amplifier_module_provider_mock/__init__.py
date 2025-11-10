"""
Mock provider module for testing.
Returns pre-configured responses without calling real APIs.
"""

import logging
from typing import Any
from typing import Optional

from amplifier_core import ModuleCoordinator
from amplifier_core import ProviderResponse
from amplifier_core import ToolCall

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

    def __init__(self, config: dict[str, Any], coordinator: ModuleCoordinator | None = None):
        self.responses = config.get(
            "responses",
            ["I'll help you with that task.", "Task completed successfully.", "Here's the result of your request."],
        )
        self.call_count = 0
        self.coordinator = coordinator
        self.debug = config.get("debug", False)
        self.raw_debug = config.get("raw_debug", False)

    async def complete(self, messages: list[dict[str, Any]], **kwargs) -> ProviderResponse:
        """Generate a mock completion."""
        self.call_count += 1

        # RAW DEBUG: Complete mock request (ultra-verbose)
        if self.coordinator and hasattr(self.coordinator, "hooks") and self.debug and self.raw_debug:
            await self.coordinator.hooks.emit(
                "llm:request:raw",
                {
                    "lvl": "DEBUG",
                    "data": {
                        "provider": "mock",
                        "messages": messages,
                        "kwargs": kwargs,
                        "call_count": self.call_count,
                    },
                },
            )

        # Check if we should return a tool call
        last_message = messages[-1] if messages else {}
        content = last_message.get("content", "")

        # Generate mock response
        response = None
        # Simple pattern matching for tool calls
        if "read" in content.lower():
            response = ProviderResponse(
                content="", raw=None, tool_calls=[ToolCall(tool="read", arguments={"path": "test.txt"})]
            )
        else:
            # Return a regular response
            response_text = self.responses[self.call_count % len(self.responses)]
            response = ProviderResponse(content=response_text, raw=None, usage={"input": 10, "output": 20})

        # RAW DEBUG: Complete mock response (ultra-verbose)
        if self.coordinator and hasattr(self.coordinator, "hooks") and self.debug and self.raw_debug:
            await self.coordinator.hooks.emit(
                "llm:response:raw",
                {
                    "lvl": "DEBUG",
                    "data": {
                        "provider": "mock",
                        "response": {
                            "content": response.content,
                            "tool_calls": [{"tool": tc.tool, "arguments": tc.arguments} for tc in response.tool_calls]
                            if response.tool_calls
                            else None,
                            "usage": response.usage,
                        },
                    },
                },
            )

        return response

    def parse_tool_calls(self, response: ProviderResponse) -> list[ToolCall]:
        """Parse tool calls from response."""
        return response.tool_calls or []
