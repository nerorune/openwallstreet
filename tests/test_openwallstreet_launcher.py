"""Smoke tests for the user-facing launcher command surface."""

from pathlib import Path
import subprocess

from trader.mmr_cli import build_parser
from trader import openwallstreet_tui
from trader.tui import run_tui
from trader.tui import run_tui


ROOT = Path(__file__).resolve().parents[1]


def test_tui_settings_cli_flag_is_parsed() -> None:
    args = build_parser().parse_args(["tui", "--settings"])
    assert args.settings is True


def test_launcher_help_advertises_tui_and_settings() -> None:
    result = subprocess.run(
        [str(ROOT / "scripts" / "openwallstreet"), "--help"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "--tui" in result.stdout
    assert "--settings" in result.stdout
    assert "gateway" in result.stdout
    assert "restart" in result.stdout
    assert "rebuild" in result.stdout


def test_launcher_commands_lists_extension_hook() -> None:
    result = subprocess.run(
        [str(ROOT / "scripts" / "openwallstreet"), "commands"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "Local extensions" in result.stdout
    assert "--settings" in result.stdout


def test_launcher_doctor_help_is_available() -> None:
    result = subprocess.run(
        [str(ROOT / "scripts" / "openwallstreet"), "doctor", "--help"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "doctor" in result.stdout
    assert "--strict" not in result.stderr


def test_public_tui_entrypoint_uses_openwallstreet_control_center(monkeypatch) -> None:
    seen = {}

    def fake_run(*, demo, watchlist, open_settings):
        seen.update(demo=demo, watchlist=watchlist, open_settings=open_settings)

    monkeypatch.setattr(openwallstreet_tui, "run_openwallstreet_tui", fake_run)
    run_tui(demo=True, watchlist=["AAPL"], open_settings=True)
    assert seen == {"demo": True, "watchlist": ["AAPL"], "open_settings": True}


def test_launcher_starts_the_configured_mode_instead_of_forcing_paper() -> None:
    launcher = (ROOT / "scripts" / "openwallstreet").read_text(encoding="utf-8")
    assert 'exec ./start_mmr.sh --$mode' in launcher
    assert 'exec ./start_mmr.sh --paper' not in launcher


def test_public_tui_entrypoint_uses_openwallstreet_terminal(monkeypatch) -> None:
    import trader.openwallstreet_tui as product_tui

    seen = {}

    def fake_run(*, demo, watchlist, open_settings):
        seen.update(demo=demo, watchlist=watchlist, open_settings=open_settings)

    monkeypatch.setattr(product_tui, "run_openwallstreet_tui", fake_run)
    run_tui(demo=True, watchlist=["QQQ"], open_settings=True)
    assert seen == {"demo": True, "watchlist": ["QQQ"], "open_settings": True}


def test_launcher_starts_the_configured_mode_instead_of_forcing_paper() -> None:
    launcher = (ROOT / "scripts" / "openwallstreet").read_text(encoding="utf-8")
    assert 'exec ./start_mmr.sh --$mode' in launcher
    assert 'exec ./start_mmr.sh --paper' not in launcher
