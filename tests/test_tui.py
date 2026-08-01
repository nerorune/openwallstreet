"""Focused non-interactive coverage for the Textual MMR client."""

import pytest

from trader.tui import DemoBackend, MMRTerminal, _data_state


def test_demo_backend_is_deterministic_and_explicitly_not_broker() -> None:
    first = DemoBackend().refresh(["QQQ"])
    second = DemoBackend().refresh(["QQQ"])
    assert first.connected is second.connected is True
    assert first.quotes["QQQ"]["data_type"] == "DEMO"
    assert _data_state(first.quotes["QQQ"]) == "DEMO"


@pytest.mark.asyncio
async def test_demo_tui_renders_paper_dashboard() -> None:
    app = MMRTerminal(demo=True, watchlist=["QQQ", "AAPL"])
    async with app.run_test() as pilot:
        await pilot.pause(0.25)
        assert "PAPER ONLY" in str(app.query_one("#topline").render())
        assert app.query_one("#watchlist").row_count == 2
        await pilot.press("d")
        assert "Doctor:" in str(app.query_one("#activity").render())
