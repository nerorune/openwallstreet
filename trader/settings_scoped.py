"""Section-scoped apply/discard behavior for production Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, Label
from textual.widgets import Static

from trader.settings import CredentialStore, MMRConfigStore, SettingsError, validate_risk_limits
from trader.settings_doctor import DiagnosticResult, DiagnosticsDoctor
from trader.settings_screen import SECTION_DESCRIPTIONS, SECTIONS, SettingsRow, SettingsScreen
from trader.settings_store import UISettings, UISettingsError


class CredentialReplacementScreen(ModalScreen[tuple[str, str, bool] | None]):
    """Collect replacement Gateway credentials without reading old values."""

    BINDINGS = [("ctrl+s", "save", "Replace"), ("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Replace Gateway credentials"),
            Static("Existing values are never read, pre-filled, logged, or displayed."),
            Input(placeholder="IBKR username", password=True, id="credential-username"),
            Input(placeholder="IBKR password", password=True, id="credential-password"),
            Input(placeholder="Type REPLACE", password=True, id="credential-confirm"),
            Static("Ctrl+S replaces both values. Then run `openwallstreet auth` for Gateway login and MFA.", classes="settings-help"),
            id="settings-confirm",
        )

    def action_save(self) -> None:
        self.dismiss((
            self.query_one("#credential-username", Input).value,
            self.query_one("#credential-password", Input).value,
            self.query_one("#credential-confirm", Input).value == "REPLACE",
        ))

    def action_cancel(self) -> None:
        self.dismiss(None)


class RiskLimitsEditor(ModalScreen[dict[str, str] | None]):
    """Edit the supported backend risk limits, then apply them through MMR."""

    BINDINGS = [("ctrl+s", "save", "Stage"), ("escape", "cancel", "Cancel")]

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__()
        self.values = values
        self.keys = tuple(sorted(values))

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Risk limits"),
            Static("Changes are validated, applied through the MMR RPC when available, and saved for restart."),
            *(Input(str(self.values[key]), placeholder=key, id=f"risk-{key}") for key in self.keys),
            Static("Ctrl+S stages every value. Esc leaves all values unchanged.", classes="settings-help"),
            id="settings-confirm",
        )

    def action_save(self) -> None:
        self.dismiss({key: self.query_one(f"#risk-{key}", Input).value for key in self.keys})

    def action_cancel(self) -> None:
        self.dismiss(None)


class TradingModeScreen(ModalScreen[str | None]):
    """Require an explicit typed selection before changing the next-session mode."""

    BINDINGS = [("ctrl+s", "save", "Save"), ("escape", "cancel", "Cancel")]

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Trading mode for the next service start"),
            Static(
                "Choose paper or live. Live here means live-account monitoring only: execution remains "
                "locked and the Gateway stays read-only."
            ),
            Input(value=self.current.lower(), placeholder="paper or live", id="trading-mode"),
            Input(placeholder="Type LIVE when selecting live", password=True, id="live-mode-confirm"),
            Static("Ctrl+S saves this next-session choice. Then run `openwallstreet auth` to align Gateway login/MFA.", classes="settings-help"),
            id="settings-confirm",
        )

    def action_save(self) -> None:
        mode = self.query_one("#trading-mode", Input).value.strip().lower()
        confirmed = self.query_one("#live-mode-confirm", Input).value == "LIVE"
        # Typing LIVE is itself the explicit selection, which also makes the
        # keyboard-only path unambiguous when the first field retains paper.
        if confirmed and mode in {"", "paper", "live"}:
            self.dismiss("live")
        else:
            self.dismiss(mode if mode == "paper" else "")

    def action_cancel(self) -> None:
        self.dismiss(None)


class ProductionDiagnosticsDoctor(DiagnosticsDoctor):
    @property
    def config(self) -> dict[str, object]:
        return dict(getattr(self.app, "settings_config", {}))

    @property
    def config_path(self):
        return Path(getattr(self.app, "settings_config_path"))

    @property
    def secrets_path(self) -> Path:
        return Path(getattr(self.app, "settings_secrets_path"))

    def check_config(self) -> DiagnosticResult:
        if getattr(self.app.backend, "is_demo", False):
            return DiagnosticResult(
                "config",
                "Trader configuration",
                "PASS",
                "Demo configuration is isolated in memory.",
                (str(self.config_path),),
            )
        return super().check_config()


class ProductionSettingsScreen(SettingsScreen):
    """Keep Watchlist and Appearance drafts independent."""

    def __init__(self, app_ref):
        super().__init__(app_ref)
        self.doctor = ProductionDiagnosticsDoctor(app_ref, self.locator)

    def _config(self) -> dict[str, object]:
        return dict(getattr(self.app_ref, "settings_config", {}))

    def _rows(self) -> list[SettingsRow]:
        if self.category == "Risk Limits":
            limits = self._config().get("risk_limits", {})
            if not isinstance(limits, dict):
                limits = {}
            rows = [SettingsRow("Edit risk limits", "Press Enter", "Editable", "action", "risk-limits-edit")]
            rows.extend(
                SettingsRow(str(key).replace("_", " ").title(), str(value))
                for key, value in sorted(limits.items())
            )
            return rows
        if self.category == "Trading Safety":
            rows = super()._rows()
            if rows:
                rows[0] = SettingsRow("Trading mode", rows[0].value, "Editable", "action", "trading-mode-edit")
            return rows
        if self.category != "Credentials":
            return super()._rows()
        secrets = Path(self.app_ref.settings_secrets_path)
        gateway_env = Path(self.app_ref.settings_gateway_env_path)

        def status(path: Path) -> str:
            if not path.exists():
                return "Not present"
            try:
                return f"Present · {path.stat().st_mode & 0o777:04o}"
            except OSError:
                return "Present · unreadable metadata"

        return [
            SettingsRow("Services secrets", status(secrets)),
            SettingsRow("Gateway environment", status(gateway_env)),
            SettingsRow("Stored values", "Never displayed", "Locked"),
            SettingsRow("Replace Gateway credentials", "Press Enter", "Editable", "action", "credentials-replace"),
            SettingsRow("Authenticate Gateway", "openwallstreet auth", "External action"),
        ]

    def _activate(self) -> None:
        rows = self._rows()
        if not rows:
            return
        row = rows[self.row_index]
        if row.key == "credentials-replace":
            self.app.push_screen(CredentialReplacementScreen(), self._replace_credentials)
            return
        if row.key == "risk-limits-edit":
            limits = self._config().get("risk_limits", {})
            if not isinstance(limits, dict) or not limits:
                limits = {"max_daily_loss": 1000.0, "max_open_orders": 10, "max_leverage": 1.0}
            self.app.push_screen(RiskLimitsEditor(limits), self._save_risk_limits)
            return
        if row.key == "trading-mode-edit":
            self.app.push_screen(TradingModeScreen(row.value), self._save_trading_mode)
            return
        super()._activate()

    def _replace_credentials(self, values: tuple[str, str, bool] | None) -> None:
        if values is None:
            return
        try:
            CredentialStore(Path(self.app_ref.settings_gateway_env_path)).replace_gateway_credentials(
                values[0], values[1], confirmed=values[2]
            )
        except SettingsError as exc:
            self.message = f"Credentials were not replaced: {exc}"
        else:
            self.message = "Credentials replaced securely. Run `openwallstreet auth` to start Gateway login and MFA."
        self.render_settings()

    def _save_risk_limits(self, values: dict[str, str] | None) -> None:
        if values is None:
            return
        try:
            changes = validate_risk_limits(values)
            if not getattr(self.app_ref.backend, "is_demo", False):
                callback = getattr(self.app_ref.backend, "set_risk_limits", None)
                if callback is None:
                    raise SettingsError("MMR risk RPC is unavailable; no values were saved.")
                updated = dict(callback(**changes))
            else:
                updated = changes
            config_store = MMRConfigStore(Path(self.app_ref.settings_config_path))
            # Demo settings intentionally begin in memory. Preserve that full
            # snapshot instead of replacing it with a file containing only the
            # edited risk section.
            config = config_store.load() or dict(self.app_ref.settings_config)
            config["risk_limits"] = updated
            config_store.save(config)
            self.app_ref.settings_config = config
        except (SettingsError, OSError, ValueError) as exc:
            self.message = f"Risk limits were not changed: {exc}"
        else:
            self.message = "Risk limits applied through MMR and saved for the next start."
        self.render_settings()

    def _save_trading_mode(self, mode: str | None) -> None:
        if mode is None:
            return
        if mode not in {"paper", "live"}:
            self.message = "Mode was not changed: enter paper, or type LIVE to confirm live monitoring."
            self.render_settings()
            return
        try:
            store = MMRConfigStore(Path(self.app_ref.settings_config_path))
            config = store.load() or dict(self.app_ref.settings_config)
            config["trading_mode"] = mode
            store.save(config)
            self.app_ref.settings_config = config
        except OSError as exc:
            self.message = f"Mode was not saved: {type(exc).__name__}."
        else:
            self.message = (
                f"{mode.upper()} selected for the next start. Execution remains locked; run `openwallstreet auth` "
                "to align the Gateway and complete MFA."
            )
        self.render_settings()

    def _watchlist_pending(self) -> bool:
        source, symbols, _theme, _dense, _unicode = self._saved_snapshot
        return self.watchlist_source != source or tuple(self.watchlist_symbols) != symbols

    def _appearance_pending(self) -> bool:
        _source, _symbols, theme, dense, unicode_symbols = self._saved_snapshot
        return (
            self.theme_name != theme
            or self.dense != dense
            or self.unicode_symbols != unicode_symbols
        )

    def _section_pending(self, category: str | None = None) -> bool:
        category = category or self.category
        if category == "Watchlist":
            return self._watchlist_pending()
        if category == "Appearance":
            return self._appearance_pending()
        return False

    def _pending(self) -> bool:
        return self._watchlist_pending() or self._appearance_pending()

    def _render_sections(self) -> Text:
        width = max(32, self.query_one("#settings-sections", Static).size.width or 64)
        name_width = 23
        description_width = max(0, width - name_width - 7)
        text = Text()
        for index, section in enumerate(SECTIONS):
            selected = index == self.section_index
            marker = "›" if selected and self.pane == "sections" else "•" if selected else " "
            pending = "*" if self._section_pending(section) else " "
            line = f" {marker} {section:<{name_width}} {pending}"
            if selected and self.pane == "sections":
                text.append(line, style="bold reverse")
            elif selected:
                text.append(line, style="bold cyan")
            elif pending == "*":
                text.append(line, style="yellow")
            else:
                text.append(line, style="dim")
            if description_width:
                text.append(
                    f"  {self._clip(SECTION_DESCRIPTIONS[section], description_width):<{description_width}}",
                    style="italic dim",
                )
            text.append("\n")
        return text

    def _apply(self) -> None:
        category = self.category
        if not self._section_pending(category):
            self.message = f"No pending edits in {category}."
            self.render_settings()
            return

        saved_source, saved_symbols, saved_theme, saved_dense, saved_unicode = self._saved_snapshot
        try:
            if category == "Watchlist":
                if self.watchlist_source == "IBKR":
                    self.message = (
                        "Apply blocked: the current MMR SDK does not expose broker watchlists. "
                        "Switch back to MANUAL to save."
                    )
                    self.render_settings()
                    return
                settings = UISettings(
                    watchlist_source=self.watchlist_source,
                    manual_symbols=list(self.watchlist_symbols),
                    symbol_history=list(self.store.settings.symbol_history),
                    theme=self.store.settings.theme,
                    dense=self.store.settings.dense,
                    unicode_symbols=self.store.settings.unicode_symbols,
                )
                self.store.settings = settings
                self.store.update_history(self.watchlist_symbols)
                self.store.save(self.store.settings)
                self.app_ref.watchlist = list(self.watchlist_symbols)
                self._saved_snapshot = (
                    self.watchlist_source,
                    tuple(self.watchlist_symbols),
                    saved_theme,
                    saved_dense,
                    saved_unicode,
                )
                self.message = "Watchlist applied and saved locally."
                self.app_ref.action_refresh()
            elif category == "Appearance":
                settings = UISettings(
                    watchlist_source=self.store.settings.watchlist_source,
                    manual_symbols=list(self.store.settings.manual_symbols),
                    symbol_history=list(self.store.settings.symbol_history),
                    theme=self.theme_name,
                    dense=self.dense,
                    unicode_symbols=self.unicode_symbols,
                )
                self.store.save(settings)
                self.app_ref.theme = self.theme_name
                self.app_ref.set_class(self.dense, "dense")
                self._saved_snapshot = (
                    saved_source,
                    saved_symbols,
                    self.theme_name,
                    self.dense,
                    self.unicode_symbols,
                )
                self.message = "Appearance settings applied."
        except (OSError, UISettingsError) as exc:
            self.message = f"{category} was not saved: {type(exc).__name__}: {exc}"
        self.render_settings()

    def _discard(self) -> None:
        category = self.category
        saved_source, saved_symbols, saved_theme, saved_dense, saved_unicode = self._saved_snapshot
        if category == "Watchlist":
            self.watchlist_source = saved_source
            self.watchlist_symbols = list(saved_symbols)
            self.message = "Pending Watchlist edits discarded."
        elif category == "Appearance":
            self.theme_name = saved_theme
            self.dense = saved_dense
            self.unicode_symbols = saved_unicode
            self.app_ref.theme = saved_theme
            self.app_ref.set_class(saved_dense, "dense")
            self.message = "Pending Appearance edits discarded."
        else:
            self.message = f"No editable draft in {category}."
        self.render_settings()

    def on_key(self, event: events.Key) -> None:
        if (
            not self.editing
            and self.pane == "sections"
            and event.key in {"escape", "left"}
            and self._pending()
        ):
            self.message = "Pending edits remain. Open the marked section, then press A to apply or D to discard."
            self.render_settings()
            event.stop()
            event.prevent_default()
            return
        super().on_key(event)
