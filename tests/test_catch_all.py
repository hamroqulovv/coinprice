"""Unit tests: catch_all routing (main.py).

- Unregistered + private -> onboarding via start_bot (no "/start" detour).
- Unregistered + group -> short private-chat hint, no state change.
- Registered + ticker -> straight to search_coin (never a register prompt).
- Registered + gibberish -> generic "tushunarsiz" reply.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main as m


def _msg(text, uid=777, chat_type="private"):
    msg = MagicMock()
    msg.text = text
    msg.from_user.id = uid
    msg.chat.type = chat_type
    msg.answer = AsyncMock()
    return msg


def _state():
    st = MagicMock()
    st.clear = AsyncMock()
    st.set_state = AsyncMock()
    return st


def test_unregistered_private_goes_to_onboarding():
    msg, st = _msg("BTC"), _state()
    with patch.object(m, "is_registered", AsyncMock(return_value=False)), \
         patch.object(m, "start_bot", AsyncMock()) as start:
        import asyncio
        asyncio.run(m.catch_all(msg, st))
    assert start.await_count == 1
    assert msg.answer.await_count == 0  # "/start bosing" xabari yo'q


def test_unregistered_group_gets_hint_only():
    msg, st = _msg("BTC", chat_type="group"), _state()
    with patch.object(m, "is_registered", AsyncMock(return_value=False)), \
         patch.object(m, "start_bot", AsyncMock()) as start:
        import asyncio
        asyncio.run(m.catch_all(msg, st))
    assert start.await_count == 0
    out = msg.answer.await_args.args[0]
    assert "shaxsiy chat" in out


def test_registered_ticker_goes_straight_to_search():
    msg, st = _msg("eth", uid=1), _state()
    with patch.object(m, "is_registered", AsyncMock(return_value=True)), \
         patch.object(m, "search_coin", AsyncMock()) as sc, \
         patch.object(m, "start_bot", AsyncMock()) as start:
        import asyncio
        asyncio.run(m.catch_all(msg, st))
    assert sc.await_count == 1
    assert start.await_count == 0
    assert msg.answer.await_count == 0  # register prompt yo'q


def test_registered_gibberish_gets_generic_reply():
    msg, st = _msg("salom dunyo", uid=1), _state()
    with patch.object(m, "is_registered", AsyncMock(return_value=True)), \
         patch.object(m, "search_coin", AsyncMock()) as sc:
        import asyncio
        asyncio.run(m.catch_all(msg, st))
    out = msg.answer.await_args.args[0]
    assert "Tushunarsiz" in out
    assert sc.await_count == 0
