"""Unit coverage for OpenWallStreet Settings persistence, themes, and process safety."""

from __future__ import annotations

from pathlib import Path

import json

import pytest

from trader.settings_health import DashboardProcessLocator
from trader.settings_store import MAX_WATCHLIST_SYMBOLS, UISettings, UISettingsError, UISettingsStore
from trader.settings_themes import THEMES, normalize_theme, theme_label


def test_ui_settings_normalize_limit_and_persist_atomically(tmp_path: Path) -> None:
    path = tmp_path / "ui.json"
    store = UISettingsStore(path)
    symbols = ["aapl", "mstr", "brk.b", "btc-usd"]
    store.save(UISettings(manual_symbols=store.normalize_symbols(symbols), theme="nord"))

    loaded = UISettingsStore(path)
    assert loaded.settings.manual_symbols == ["AAPL", "MSTR", "BRK.B", "BTC-USD"]
    assert loaded.settings.theme == "nord"
    assert path.stat().st_mode & 0o777 == 0o600

    with pytest.raises(UISettingsError):
        store.normalize_symbol("../AAPL")
    with pytest.raises(UISettingsError):
        store.normalize_symbols([f"S{index}" for index in range(MAX_WATCHLIST_SYMBOLS + 1)])


def test_ui_settings_recovers_last_valid_backup(tmp_path: Path) -> None:
    path = tmp_path / "ui.json"
    store = UISettingsStore(path)
    store.save(UISettings(manual_symbols=["AAPL"]))
    store.save(UISettings(manual_symbols=["AAPL", "MSFT"]))
    path.write_text("{broken", encoding="utf-8")

    recovered = UISettingsStore(path)
    assert recovered.settings.manual_symbols == ["AAPL"]
    assert "Recovered" in recovered.load_warning


def test_symbol_history_is_ranked_and_deduplicated(tmp_path: Path) -> None:
    store = UISettingsStore(tmp_path / "ui.json")
    store.settings.manual_symbols = ["AAPL", "MSFT"]
    store.update_history(["AAPL", "MSFT"])
    store.update_history(["AAPL"])
    assert store.suggestions()[:2] == ["AAPL", "MSFT"]
    assert store.settings.symbol_history[0].usage_count == 2


def test_theme_registry_contains_real_unique_textual_themes() -> None:
    names = [definition.name for definition in THEMES]
    labels = [definition.label for definition in THEMES]
    assert len(names) >= 10
    assert len(names) == len(set(names))
    assert len(labels) == len(set(labels))
    assert normalize_theme("Nord") == "nord"
    assert normalize_theme("missing") == "openwallstreet-dark"
    assert theme_label("terminal-green") == "Terminal Green"
    assert all(definition.theme.name == definition.name for definition in THEMES)


class _FakeProcess:
    def __init__(self, pid: int, cmdline: list[str], cwd: Path, create_time: float) -> None:
        self.info = {
            "pid": pid,
            "cmdline": cmdline,
            "cwd": str(cwd),
            "create_time": create_time,
        }


def test_dashboard_locator_ignores_unrelated_python_and_plans_exact_duplicates(tmp_path: Path) -> None:
    processes = [
        _FakeProcess(101, ["uv", "run", "mmr", "tui"], tmp_path, 10.0),
        _FakeProcess(102, ["python", "-m", "trader.mmr_cli", "tui"], tmp_path, 20.0),
        _FakeProcess(103, ["python", "important_worker.py"], tmp_path, 30.0),
    ]
    locator = DashboardProcessLocator(
        tmp_path,
        current_pid=101,
        process_iter=lambda _attrs: processes,
        now=lambda: 100.0,
    )

    health = locator.health()
    assert health.status == "DEGRADED"
    assert health.pids == (101, 102)
    plan = locator.duplicate_plan()
    assert plan is not None
    assert plan.pids == (102,)
    assert "important_worker.py" not in " ".join(plan.commands)


def test_ui_json_is_schema_versioned(tmp_path: Path) -> None:
    path = tmp_path / "ui.json"
    UISettingsStore(path).save(UISettings(manual_symbols=["QQQ"]))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
