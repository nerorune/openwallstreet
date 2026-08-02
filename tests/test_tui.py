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
        assert "PAPER ACCOUNT" in str(app.query_one("#topline").render())
        assert "EXECUTION LOCKED" in str(app.query_one("#topline").render())
        assert app.query_one("#watchlist").row_count == 2
        await pilot.press("d")
        assert "OpenWallStreet diagnostics" in str(app.screen.query_one("#diagnostics-title").render())


@pytest.mark.asyncio
async def test_demo_tui_opens_settings_with_keyboard_and_narrow_layout() -> None:
    app = MMRTerminal(demo=True)
    async with app.run_test(size=(70, 24)) as pilot:
        await pilot.pause(0.05)
        await pilot.press("s")
        await pilot.pause(0.05)
        assert "Settings control center" in str(app.screen.query_one("#settings-title").render())
        await pilot.press("j", "j")
        assert "Credentials" in str(app.screen.query_one("#settings-detail").render())
        assert app.screen.has_class("settings-compact")


@pytest.mark.asyncio
async def test_tui_can_open_directly_in_settings() -> None:
    app = MMRTerminal(demo=True, open_settings=True)
    async with app.run_test() as pilot:
        await pilot.pause(0.05)
        assert "Settings control center" in str(app.screen.query_one("#settings-title").render())


@pytest.mark.asyncio
async def test_settings_opens_risk_editor_with_keyboard() -> None:
    app = MMRTerminal(demo=True, open_settings=True)
    async with app.run_test() as pilot:
        await pilot.pause(0.05)
        await pilot.press("j", "j", "j", "j", "j", "e")
        await pilot.pause(0.05)
        assert app.screen.query_one("#risk-max_daily_loss").value


@pytest.mark.asyncio
async def test_native_command_palette_exposes_workstation_actions() -> None:
    app = MMRTerminal(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.05)
        assert "CommandPalette" in type(app.screen).__name__
        await pilot.press("escape")
