"""Config hygiene tests: bool coercion, debug/raw_debug collapse, the
responses-rotation off-by-one fix, and the unknown-key sweep.

Guards the "family hygiene wave" fixes for provider-mock:
  - debug/use_streaming previously used bare truthiness (``bool("false")``
    is ``True`` in Python).
  - debug AND raw_debug used to be required together to enable raw event
    emission; debug ALONE now enables it, raw_debug is an accepted alias.
  - responses rotation had an off-by-one: call 1 returned responses[1],
    not responses[0], because call_count was incremented before indexing.
"""

from __future__ import annotations

import logging

import pytest
from amplifier_core.message_models import ChatRequest, Message

import amplifier_module_provider_mock as _provider_module

MockProvider = _provider_module.MockProvider
# Module-private helpers -- no public contract; some static analyzers fail
# to resolve underscore-prefixed module attrs via `from X import _name`.
_coerce_bool = _provider_module._coerce_bool  # type: ignore[attr-defined]
_warn_unknown_config_keys = _provider_module._warn_unknown_config_keys  # type: ignore[attr-defined]


class FakeHooks:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    async def emit(self, name, payload):
        self.events.append((name, payload))


class FakeCoordinator:
    def __init__(self):
        self.hooks = FakeHooks()


def _request(text: str = "hello") -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content=text)])


class TestCoerceBool:
    def test_string_false_is_false(self):
        assert _coerce_bool("false", key="x", default=True) is False

    def test_string_true_is_true(self):
        assert _coerce_bool("true", key="x", default=False) is True

    def test_unrecognized_string_warns_and_defaults(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _coerce_bool("maybe", key="debug", default=True)
        assert result is True
        assert "debug" in caplog.text


class TestUnknownConfigKeySweep:
    def test_known_keys_silent(self, caplog):
        with caplog.at_level(logging.WARNING):
            _warn_unknown_config_keys({"responses": [], "priority": 1})
        assert caplog.text == ""

    def test_stray_delay_key_suggests_stream_delay_ms(self, caplog):
        """The documented victim: foundation's notebook passes a dead
        `delay` key -- its did-you-mean should suggest stream_delay_ms."""
        with caplog.at_level(logging.WARNING):
            _warn_unknown_config_keys({"delay": 100})
        assert "delay" in caplog.text
        assert "stream_delay_ms" in caplog.text


class TestProviderConfigCoercionIntegration:
    def test_debug_string_false_is_false(self):
        provider = MockProvider({"debug": "false"})
        assert provider.debug is False

    def test_use_streaming_string_false_is_false(self):
        provider = MockProvider({"use_streaming": "false"})
        assert getattr(provider, "use_streaming") is False  # noqa: B009

    def test_debug_alone_enables_raw_events(self):
        """debug: true ALONE (no raw_debug) now enables raw event emission."""
        provider = MockProvider({"debug": True, "use_streaming": False})
        assert provider.debug is True
        assert provider.raw_debug is False

    def test_raw_debug_alone_is_accepted_alias(self, caplog):
        """raw_debug: true without debug still enables raw events (with a
        warning), preserving backwards compatibility."""
        with caplog.at_level(logging.WARNING):
            provider = MockProvider({"raw_debug": True})
        assert provider.debug is True
        assert "alias" in caplog.text or "no longer requires" in caplog.text

    @pytest.mark.asyncio
    async def test_debug_alone_actually_emits_raw_events(self):
        """End-to-end: debug=true, raw_debug unset, still emits llm:request:raw."""
        coordinator = FakeCoordinator()
        provider = MockProvider(
            {"debug": True, "use_streaming": False},
            coordinator,  # type: ignore[arg-type]
        )
        await provider.complete(_request())
        event_names = [name for name, _ in coordinator.hooks.events]
        assert "llm:request:raw" in event_names
        assert "llm:response:raw" in event_names


class TestResponseRotationOffByOne:
    """The bug: call_count was incremented BEFORE indexing, so the first
    call returned responses[1] instead of responses[0]."""

    @pytest.mark.asyncio
    async def test_first_call_returns_first_response(self):
        coordinator = FakeCoordinator()
        provider = MockProvider(
            {"responses": ["FIRST", "SECOND", "THIRD"], "use_streaming": False},
            coordinator,  # type: ignore[arg-type]
        )
        response = await provider.complete(_request())
        assert getattr(response.content[0], "text", None) == "FIRST"

    @pytest.mark.asyncio
    async def test_rotation_order_across_multiple_calls(self):
        coordinator = FakeCoordinator()
        provider = MockProvider(
            {"responses": ["FIRST", "SECOND", "THIRD"], "use_streaming": False},
            coordinator,  # type: ignore[arg-type]
        )
        texts = []
        for _ in range(4):
            response = await provider.complete(_request())
            texts.append(getattr(response.content[0], "text", None))
        assert texts == ["FIRST", "SECOND", "THIRD", "FIRST"]
