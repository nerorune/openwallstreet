"""Keyboard-first Textual views for the OpenWallStreet settings domain."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from trader.settings import CredentialStore, LiveExecutionRequest, SettingsDraft, SettingsError, validate_live_execution_request


CATEGORIES = (
    "Overview", "Gateway & Login", "Credentials", "Account & Data",
    "Trading Safety", "Risk Limits", "Watchlist", "Appearance",
    "Diagnostics", "Advanced Config",
)


class DiagnosticsScreen(ModalScreen[None]):
    """Read-only operational summary rendered from the terminal's MMR state."""

    BINDINGS = [("r", "refresh", "Refresh"), ("escape", "close", "Close")]

    def __init__(self, terminal: Any) -> None:
        super().__init__()
        self.terminal = terminal

    def compose(self) -> ComposeResult:
        yield Container(
            Label("OpenWallStreet diagnostics", id="diagnostics-title"),
            Static(id="diagnostics-summary"),
            Static("R refreshes the dashboard • Esc returns to the workstation", id="confirm-help"),
            id="diagnostics",
        )

    def on_mount(self) -> None:
        self.render_summary()

    def render_summary(self) -> None:
        state = self.terminal.state
        backend = "deterministic demo (no broker)" if self.terminal.backend.is_demo else "MMR SDK/RPC only"
        connection = "CONNECTED" if state.connected else "DISCONNECTED"
        upstream = state.service_error or "no reported upstream error"
        self.query_one("#diagnostics-summary", Static).update(
            f"Backend: {backend}\n"
            f"Connection: {connection}\n"
            f"Account: {state.account[-4:] if state.account else 'not selected'}\n"
            f"Mode: {state.trading_mode}\n"
            f"Execution: {'ENABLED' if state.execution_enabled else 'LOCKED'}\n"
            f"Gateway / MMR detail: {upstream}\n\n"
            "Safety boundary: this UI never opens a direct IBKR connection; "
            "all state comes through the included MMR-derived SDK/RPC layer."
        )

    def action_refresh(self) -> None:
        self.terminal.action_refresh()
        self.render_summary()

    def action_close(self) -> None:
        self.dismiss(None)


class SettingsScreen(ModalScreen[None]):
    """A draft-only settings center. Its app reference stays on the MMR SDK path."""

    BINDINGS = [
        ("j", "next", "Next"), ("down", "next", "Next"),
        ("k", "previous", "Previous"), ("up", "previous", "Previous"),
        ("e", "edit", "Edit"), ("a", "apply", "Apply"),
        ("d", "discard", "Discard"), ("escape", "close", "Close"),
    ]

    def __init__(self, terminal: Any) -> None:
        super().__init__()
        self.terminal = terminal
        self.draft = SettingsDraft.open()
        self.index = 0
        self.message = "Draft-first editing: Apply or Discard explicitly."

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Settings control center | DARK OPERATIONAL THEME", id="settings-title"),
            Static(id="settings-categories"),
            Static(id="settings-detail"),
            Static(id="settings-review"), id="settings")

    def on_mount(self) -> None:
        self.render_settings()

    def on_resize(self, event) -> None:
        self.set_class(event.size.width < 80, "settings-compact")

    def render_settings(self) -> None:
        category = CATEGORIES[self.index]
        self.query_one("#settings-categories", Static).update(
            "\n".join(f"{'›' if item == category else ' '} {item}" for item in CATEGORIES))
        credential = CredentialStore().health()
        risk = self.draft.mmr.risk_limits() | self.draft.risk_changes
        content = {
            "Overview": f"MMR backend: {'demo' if self.terminal.backend.is_demo else 'SDK/RPC'}\nExecution: {'ENABLED' if self.terminal.state.execution_enabled else 'LOCKED'}",
            "Gateway & Login": "localhost-only Gateway controls use the existing ./docker.sh wrapper.\nVNC: vnc://localhost:5901. MFA is required after every restart.",
            "Credentials": f"Source: {credential.source}\nPresent: {'yes' if credential.present else 'no'}\nPermissions: {credential.permissions}\nExisting values are never read or displayed.",
            "Account & Data": f"Account: {self.terminal.state.account[-4:] if self.terminal.state.account else 'not selected'}\nLive state comes only from MMR SDK/RPC.",
            "Trading Safety": "Paper changes are staged for controlled MMR restart.\nLive is locked: typed confirmation, account/mode review, risk acknowledgement, Gateway read-write restart, and MFA are all required.",
            "Risk Limits": "Supported limits (apply through MMR RPC):\n" + "\n".join(f"{key}: {value}" for key, value in sorted(risk.items())),
            "Watchlist": "UI-owned watchlist preferences apply now after confirmation.",
            "Appearance": f"Dark theme only. Dense panels: {'on' if self.draft.preferences['dense'] else 'off'}.",
            "Diagnostics": "Gateway status is reported by MMR. After a restart wait for MFA; it is never bypassed.",
            "Advanced Config": "Connection, account, data source, mode, and Gateway changes are queued until their displayed restart action is chosen.",
        }[category]
        self.query_one("#settings-detail", Static).update(f"{category}\n\n{content}\n\n{self.message}")
        diff = self.draft.diff()
        self.query_one("#settings-review", Static).update(
            f"{'DIRTY' if self.draft.dirty else 'CLEAN'} | "
            f"impact: {', '.join(i.value for i in self.draft.impacts()) or 'none'}\n" +
            ("\n".join(diff) if diff else "No pending changes.") +
            "\nJ/K navigate • E edit • A apply • D discard • Esc close")

    def action_next(self) -> None:
        self.index = min(len(CATEGORIES) - 1, self.index + 1); self.render_settings()

    def action_previous(self) -> None:
        self.index = max(0, self.index - 1); self.render_settings()

    def action_edit(self) -> None:
        category = CATEGORIES[self.index]
        if category == "Appearance":
            self.draft.toggle_dense(); self.message = "Appearance change staged; it applies now only after Apply."
        elif category == "Risk Limits":
            self.app.push_screen(
                RiskLimitScreen(self.draft.mmr.risk_limits() | self.draft.risk_changes),
                self.stage_risk,
            )
            return
        elif category == "Credentials":
            self.app.push_screen(CredentialScreen(), self.replace_credentials)
            return
        elif category == "Trading Safety":
            self.app.push_screen(
                LiveExecutionScreen(self.terminal.state.account), self.review_live,
            )
            return
        else:
            self.message = f"{category}: inspect-only. Changes are queued for the indicated restart action."
        self.render_settings()

    def stage_risk(self, values: dict[str, str] | None) -> None:
        if values:
            try:
                for key, value in values.items(): self.draft.set_risk(key, value)
                self.message = "Risk draft updated. Review and Apply to send it through MMR RPC."
            except SettingsError as exc:
                self.message = f"Validation blocked: {exc}"
        self.render_settings()

    def replace_credentials(self, values: tuple[str, str, bool] | None) -> None:
        if values:
            try:
                CredentialStore().replace_gateway_credentials(*values)
                self.message = "Credentials replaced with atomic 0600 write; restart Gateway + MFA is required."
            except SettingsError as exc:
                self.message = f"Credential update blocked: {exc}"
        self.render_settings()

    def review_live(self, request: LiveExecutionRequest | None) -> None:
        if request:
            try:
                validate_live_execution_request(request)
            except SettingsError as exc:
                self.message = f"Live remains locked: {exc}"
            else:
                self.message = "Live remains locked until an operator completes a read-write Gateway restart and MFA."
        self.render_settings()

    def action_apply(self) -> None:
        try:
            rpc = None if self.terminal.backend.is_demo else getattr(self.terminal.backend, "set_risk_limits", None)
            self.draft.apply(rpc)
            self.message = "Applied: UI preferences persisted; supported risk limits sent through MMR RPC."
        except SettingsError as exc:
            self.message = f"Apply blocked: {exc}"
        except Exception as exc:
            self.message = f"Apply failed; nothing was persisted: {type(exc).__name__}"
        self.render_settings()

    def action_discard(self) -> None:
        self.draft.discard(); self.message = "Draft discarded."; self.render_settings()

    def action_close(self) -> None:
        self.dismiss(None)


class RiskLimitScreen(ModalScreen[dict[str, str] | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]
    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(); self.values = values
    def compose(self) -> ComposeResult:
        yield Container(Label("Risk limits — draft only"),
            Input(str(self.values.get("max_daily_loss", 1000)), id="risk-max_daily_loss"),
            Input(str(self.values.get("max_open_orders", 15)), id="risk-max_open_orders"),
            Input(str(self.values.get("max_leverage", 1)), id="risk-max_leverage"),
            Static("Enter saves draft; Apply sends changes through MMR.", id="confirm-help"), id="risk-editor")
    def on_input_submitted(self) -> None:
        self.dismiss({key: self.query_one(f"#risk-{key}", Input).value for key in ("max_daily_loss", "max_open_orders", "max_leverage")})
    def action_cancel(self) -> None: self.dismiss(None)


class LiveExecutionScreen(ModalScreen[LiveExecutionRequest | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]
    def __init__(self, account: str) -> None: super().__init__(); self.account = account
    def compose(self) -> ComposeResult:
        yield Container(Label("LIVE execution — locked by default"),
            Static("Account and LIVE mode must be reviewed. Gateway is currently read-only."),
            Input(placeholder="Type ENABLE LIVE", password=True, id="live-confirm"),
            Input(placeholder="Type I ACCEPT RISK", password=True, id="live-risk"),
            Static("No order can be placed here. A Gateway restart + MFA would still be required.", id="confirm-help"), id="live-wizard")
    def on_input_submitted(self) -> None:
        self.dismiss(LiveExecutionRequest(self.account, "LIVE", self.query_one("#live-confirm", Input).value, self.query_one("#live-risk", Input).value == "I ACCEPT RISK", True))
    def action_cancel(self) -> None: self.dismiss(None)


class CredentialScreen(ModalScreen[tuple[str, str, bool] | None]):
    """Masked replacement fields; existing `.env` values are never read."""
    BINDINGS = [("escape", "cancel", "Cancel")]
    def compose(self) -> ComposeResult:
        health = CredentialStore().health()
        yield Container(Label("Gateway credentials — replacement only"), Static(f"Source: {health.source} | Present: {'yes' if health.present else 'no'} | {health.permissions}"), Input(placeholder="Username", password=True, id="credential-username"), Input(placeholder="Password", password=True, id="credential-password"), Input(placeholder="Type REPLACE to confirm", password=True, id="credential-confirm"), Static("Existing values are never pre-filled, logged, or displayed.", id="confirm-help"), id="credential-editor")
    def on_input_submitted(self) -> None:
        self.dismiss((self.query_one("#credential-username", Input).value, self.query_one("#credential-password", Input).value, self.query_one("#credential-confirm", Input).value == "REPLACE"))
    def action_cancel(self) -> None: self.dismiss(None)
