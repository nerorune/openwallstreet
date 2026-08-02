"""OpenWallStreet product TUI with the Settings control center enabled."""

from __future__ import annotations

from pathlib import Path

import argparse

from trader.settings_final import OpenWallStreetSettingsScreen
from trader.settings_store import MAX_WATCHLIST_SYMBOLS, UISettingsStore
from trader.settings_themes import normalize_theme, register_themes
from trader.tui import DEFAULT_WATCHLIST, DemoBackend, MMRTerminal


SETTINGS_CSS = """
SettingsScreen {
    align: center middle;
    background: black 55%;
}
#settings-root {
    width: 96%;
    max-width: 150;
    height: 92%;
    background: $background;
    border: solid $primary;
}
#settings-header {
    height: 4;
    padding: 0 1;
    border-bottom: solid $primary;
}
#settings-brand-block {
    width: 28;
}
#settings-brand {
    text-style: bold;
    color: $accent;
}
#settings-product, #settings-breadcrumb, .pane-kicker {
    color: $text-muted;
}
#settings-runtime {
    width: 1fr;
    text-align: right;
    padding-top: 1;
}
#settings-body {
    height: 1fr;
    padding: 1;
}
#settings-sidebar {
    width: 1fr;
    height: 1fr;
    border: solid $secondary;
    padding: 0 1;
}
#settings-workspace {
    display: none;
    width: 1fr;
    height: 1fr;
    margin-left: 1;
    border: solid $primary;
    padding: 0 1;
}
#settings-toolbar {
    height: 4;
}
#settings-heading {
    width: 1fr;
}
#settings-page-title {
    text-style: bold;
}
#settings-pending {
    display: none;
    width: auto;
    color: $warning;
    text-style: bold;
    padding-top: 1;
}
#settings-summary {
    height: 3;
    color: $text;
    text-style: bold;
}
#settings-content {
    height: 1fr;
    overflow-y: auto;
}
#settings-guidance {
    height: auto;
    min-height: 2;
    color: $text-muted;
    border-top: solid $secondary;
}
#settings-statusbar {
    height: 3;
    padding: 0 1;
    border-top: solid $primary;
    background: $panel;
}
#settings-confirm {
    width: 78;
    max-width: 94%;
    height: auto;
    max-height: 85%;
    padding: 1 2;
    border: thick $warning;
    background: $panel;
}
.settings-help {
    margin-top: 1;
    color: $text-muted;
}
SettingsScreen.settings-compact #settings-root {
    width: 100%;
    height: 100%;
}
SettingsScreen.settings-compact #settings-body {
    layout: vertical;
}
SettingsScreen.settings-compact.values-active #settings-sidebar {
    height: 7;
}
SettingsScreen.settings-compact.values-active #settings-workspace {
    margin-left: 0;
    margin-top: 1;
}
.dense DataTable {
    min-height: 5;
}
.dense #activity, .dense #qqq, .dense #account {
    padding: 0;
}
"""


class OpenWallStreetTerminal(MMRTerminal):
    """Production terminal wrapper that adds persisted settings without bypassing MMR."""

    CSS = MMRTerminal.CSS + SETTINGS_CSS
    BINDINGS = MMRTerminal.BINDINGS + [("s", "settings", "Settings")]

    def __init__(
        self,
        demo: bool = False,
        watchlist: list[str] | None = None,
        *,
        open_settings: bool = False,
        ui_store: UISettingsStore | None = None,
    ) -> None:
        # The base terminal still owns dashboard data and SDK/RPC access.  Keep
        # its legacy settings screen suppressed so every product entry point
        # uses the OpenWallStreet control center below.
        super().__init__(demo=demo, watchlist=watchlist, open_settings=False)
        self._open_settings_on_mount = open_settings
        self.ui_store = ui_store or UISettingsStore()
        explicit = [symbol.strip().upper() for symbol in (watchlist or []) if symbol.strip()]
        persisted = self.ui_store.settings.manual_symbols
        selected = explicit or persisted or list(DEFAULT_WATCHLIST)
        self.watchlist = selected[:MAX_WATCHLIST_SYMBOLS]
        self._startup_theme = normalize_theme(self.ui_store.settings.theme)

        if demo:
            config_dir = self.ui_store.path.parent
            self.settings_config = {
                "trading_mode": "paper",
                "execution_enabled": False,
                "ib_read_only": True,
                "require_proposal_approval": True,
                "ib_server_address": "127.0.0.1",
                "ib_server_port": 7497,
                "risk_limits": {
                    "max_daily_loss": 1000.0,
                    "max_open_orders": 10,
                    "max_leverage": 1.0,
                },
            }
            self.settings_config_path = config_dir / "demo-trader.yaml"
            self.settings_secrets_path = config_dir / "demo-secrets.env"
            self.settings_gateway_env_path = config_dir / "demo-gateway.env"
            self.backend.display_name = "Demo backend"
        else:
            from trader.container import Container, mmr_root

            container = Container.instance()
            self.settings_config = dict(container.config())
            self.settings_config_path = Path(container.config_file).expanduser()
            self.settings_secrets_path = Path("~/.config/mmr/secrets.env").expanduser()
            self.settings_gateway_env_path = mmr_root() / ".env"
            self.backend.display_name = "MMR SDK/RPC"

    def on_mount(self) -> None:
        register_themes(self)
        self.theme = self._startup_theme
        self.set_class(self.ui_store.settings.dense, "dense")
        super().on_mount()
        if self.ui_store.load_warning:
            self.state.note(self.ui_store.load_warning)
            self._apply_state(self.state)
        if self._open_settings_on_mount:
            self.action_settings()

    def action_settings(self) -> None:
        self.push_screen(OpenWallStreetSettingsScreen(self))


def run_openwallstreet_tui(
    demo: bool = False,
    watchlist: list[str] | None = None,
    *,
    open_settings: bool = False,
) -> None:
    OpenWallStreetTerminal(demo=demo, watchlist=watchlist, open_settings=open_settings).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the OpenWallStreet terminal with Settings.")
    parser.add_argument("--demo", action="store_true", help="Use deterministic demo data; no broker connection.")
    parser.add_argument(
        "--watchlist",
        default="",
        help="Comma-separated temporary startup watchlist; Settings may later save a manual list.",
    )
    args = parser.parse_args()
    symbols = [symbol.strip().upper() for symbol in args.watchlist.split(",") if symbol.strip()]
    run_openwallstreet_tui(demo=args.demo, watchlist=symbols or None)


if __name__ == "__main__":
    main()
