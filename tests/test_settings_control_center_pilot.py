"""Textual Pilot coverage for the production Settings control center."""

from __future__ import annotations

from pathlib import Path

import pytest

from trader.openwallstreet_tui import OpenWallStreetTerminal
from trader.settings_scoped import ProductionSettingsScreen
from trader.settings_store import UISettings, UISettingsStore


@pytest.mark.asyncio
async def test_settings_navigation_watchlist_and_appearance_are_section_scoped(tmp_path: Path) -> None:
    store = UISettingsStore(tmp_path / "ui.json")
    store.save(UISettings(manual_symbols=["QQQ"], theme="openwallstreet-dark"))
    app = OpenWallStreetTerminal(demo=True, ui_store=store)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.25)
        await pilot.press("s")
        screen = app.screen
        assert isinstance(screen, ProductionSettingsScreen)
        assert screen.pane == "sections"
        assert screen.query_one("#settings-workspace").display is False

        # Watchlist is section 7 (index 6).
        for _ in range(6):
            await pilot.press("down")
        assert screen.category == "Watchlist"
        await pilot.press("enter")
        assert screen.pane == "values"

        await pilot.press("n")
        assert screen.editing
        await pilot.press("a", "a", "p", "l", "enter")
        assert screen.watchlist_symbols == ["QQQ", "AAPL"]
        assert screen._section_pending("Watchlist")
        assert not screen._section_pending("Appearance")

        await pilot.press("a")
        assert not screen._section_pending("Watchlist")
        assert store.settings.manual_symbols == ["QQQ", "AAPL"]
        assert app.watchlist == ["QQQ", "AAPL"]

        # Appearance is the next section. Preview then discard only Appearance.
        await pilot.press("escape", "down", "enter", "down")
        assert screen.category == "Appearance"
        original_theme = app.theme
        await pilot.press("space")
        assert screen._section_pending("Appearance")
        assert app.theme != original_theme
        await pilot.press("d")
        assert not screen._section_pending("Appearance")
        assert app.theme == original_theme
        assert store.settings.manual_symbols == ["QQQ", "AAPL"]


@pytest.mark.asyncio
async def test_settings_inline_edit_and_diagnostics_do_not_touch_real_home(tmp_path: Path) -> None:
    store = UISettingsStore(tmp_path / "ui.json")
    store.save(UISettings(manual_symbols=["QQQ"]))
    app = OpenWallStreetTerminal(demo=True, ui_store=store)

    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.pause(0.25)
        await pilot.press("s")
        screen = app.screen
        assert isinstance(screen, ProductionSettingsScreen)

        # Navigate to Watchlist and verify typing is visible in the selected row.
        for _ in range(6):
            await pilot.press("down")
        await pilot.press("enter", "n", "m", "s", "f", "t")
        assert screen.editing
        assert screen._edit_value == "msft"
        rendered = str(screen.query_one("#settings-content").render())
        assert "msft" in rendered.lower()
        await pilot.press("enter", "a")
        assert store.path.exists()

        # Diagnostics uses injected demo paths and produces structured results.
        await pilot.press("escape", "down", "down", "enter", "r")
        assert screen.category == "Diagnostics"
        assert screen.diagnostic_results
        assert all(result.status in {"PASS", "WARN", "FAIL", "UNKNOWN"} for result in screen.diagnostic_results)
        assert app.settings_config_path.parent == tmp_path
        assert app.settings_secrets_path.parent == tmp_path
