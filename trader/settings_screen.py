"""Keyboard-only Settings control center for the production OpenWallStreet TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from trader.settings_doctor import DiagnosticResult, DiagnosticsDoctor, FixPlan
from trader.settings_health import DashboardProcessLocator
from trader.settings_store import MAX_WATCHLIST_SYMBOLS, UISettings, UISettingsError, UISettingsStore
from trader.settings_themes import normalize_theme, theme_label, theme_labels


SECTIONS = (
    "Overview",
    "Gateway & Login",
    "Credentials",
    "Account & Data",
    "Trading Safety",
    "Risk Limits",
    "Watchlist",
    "Appearance",
    "Diagnostics",
)

SECTION_DESCRIPTIONS = {
    "Overview": "Live process, backend, account, mode, and execution health",
    "Gateway & Login": "Gateway endpoint, restart, VNC, and MFA boundaries",
    "Credentials": "Credential locations and protection status",
    "Account & Data": "Connected account and MMR data boundary",
    "Trading Safety": "Execution switches and approval safeguards",
    "Risk Limits": "Active MMR pre-trade limits",
    "Watchlist": "Prioritized local watchlist with symbol history",
    "Appearance": "Real Textual themes and terminal presentation",
    "Diagnostics": "Structured checks and confirmed safe repairs",
}


@dataclass(frozen=True)
class SettingsRow:
    label: str
    value: str
    access: str = "Read only"
    kind: Literal["readonly", "text", "choice", "action"] = "readonly"
    key: str = ""
    options: tuple[str, ...] = ()


class ConfirmFixScreen(ModalScreen[bool]):
    BINDINGS = [
        ("y", "confirm", "Confirm"),
        ("n", "cancel", "Cancel"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, plan: FixPlan) -> None:
        super().__init__()
        self.plan = plan

    def compose(self) -> ComposeResult:
        yield Container(
            Label("CONFIRM SAFE REPAIR"),
            Static(self.plan.confirmation_text(), markup=False),
            Static("Y confirms this exact plan. N or Esc cancels.", classes="settings-help"),
            id="settings-confirm",
        )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class SettingsScreen(ModalScreen[None]):
    """Compact Settings browser connected to the production MMR-backed app."""

    def __init__(self, app_ref: Any) -> None:
        super().__init__()
        self.app_ref = app_ref
        self.store: UISettingsStore = app_ref.ui_store
        self.section_index = 0
        self.row_index = 0
        self.pane: Literal["sections", "values"] = "sections"
        self.message = "Choose a section and press Enter."
        self._edit_row: SettingsRow | None = None
        self._edit_value = ""
        self._edit_cursor = 0
        self.watchlist_source = self.store.settings.watchlist_source
        self.watchlist_symbols = list(self.store.settings.manual_symbols or app_ref.watchlist[:MAX_WATCHLIST_SYMBOLS])
        self.theme_name = normalize_theme(self.store.settings.theme)
        self.original_theme = app_ref.theme
        self.dense = self.store.settings.dense
        self.unicode_symbols = self.store.settings.unicode_symbols
        self._saved_snapshot = self._snapshot()
        self.diagnostic_results: list[DiagnosticResult] = []
        from trader.container import mmr_root

        self.locator = DashboardProcessLocator(mmr_root())
        self.doctor = DiagnosticsDoctor(app_ref, self.locator)

    @property
    def category(self) -> str:
        return SECTIONS[self.section_index]

    @property
    def editing(self) -> bool:
        return self._edit_row is not None

    def _snapshot(self) -> tuple[str, tuple[str, ...], str, bool, bool]:
        return (
            self.watchlist_source,
            tuple(self.watchlist_symbols),
            self.theme_name,
            self.dense,
            self.unicode_symbols,
        )

    def _pending(self) -> bool:
        return self._snapshot() != self._saved_snapshot

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Vertical(
                    Label("OpenWallStreet", id="settings-brand"),
                    Static("SETTINGS", id="settings-product"),
                    id="settings-brand-block",
                ),
                Static(id="settings-runtime"),
                id="settings-header",
            ),
            Horizontal(
                Vertical(
                    Static("SECTIONS", classes="pane-kicker"),
                    Static(id="settings-sections", markup=False),
                    id="settings-sidebar",
                ),
                Vertical(
                    Horizontal(
                        Vertical(
                            Static(id="settings-breadcrumb"),
                            Label(id="settings-page-title"),
                            id="settings-heading",
                        ),
                        Static(id="settings-pending"),
                        id="settings-toolbar",
                    ),
                    Static(id="settings-summary"),
                    Static(id="settings-content", markup=False),
                    Static(id="settings-guidance", markup=False),
                    id="settings-workspace",
                ),
                id="settings-body",
            ),
            Static(id="settings-statusbar", markup=False),
            id="settings-root",
        )

    def on_mount(self) -> None:
        self._set_pane("sections")
        self.render_settings()

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.width < 92, "settings-compact")
        self._set_pane(self.pane)
        self.render_settings()

    def _set_pane(self, pane: Literal["sections", "values"]) -> None:
        self.pane = pane
        self.set_class(pane == "values", "values-active")
        workspace = self.query_one("#settings-workspace", Vertical)
        sidebar = self.query_one("#settings-sidebar", Vertical)
        workspace.display = pane == "values"
        if pane == "sections":
            sidebar.styles.width = "1fr"
            sidebar.styles.height = "1fr"
        elif self.has_class("settings-compact"):
            sidebar.styles.width = "1fr"
            sidebar.styles.height = 7
        else:
            sidebar.styles.width = 28
            sidebar.styles.height = "1fr"

    def _config(self) -> dict[str, Any]:
        try:
            from trader.container import Container

            return dict(Container.instance().config())
        except Exception:
            return {}

    def _execution_label(self) -> str:
        state = self.app_ref.state
        config = self._config()
        if state.service_error:
            return "ERROR"
        if not state.connected:
            return "UNAVAILABLE"
        if not state.execution_enabled:
            return "LOCKED"
        if bool(config.get("ib_read_only", True)):
            return "READ-ONLY"
        if state.trading_mode == "PAPER":
            return "PAPER ENABLED"
        if state.trading_mode == "LIVE":
            return "LIVE ENABLED"
        return "ERROR"

    def _system_health(self) -> tuple[str, str]:
        process = self.locator.health()
        state = self.app_ref.state
        if state.service_error:
            return "ERROR", state.service_error
        if process.status == "DEGRADED":
            return "DEGRADED", process.detail
        if not state.connected and not getattr(self.app_ref.backend, "is_demo", False):
            return "DEGRADED", "MMR or IBKR is disconnected."
        if process.status == "UNKNOWN":
            return "UNKNOWN", process.detail
        return "HEALTHY", "Process and backend state are consistent."

    def _rows(self) -> list[SettingsRow]:
        state = self.app_ref.state
        config = self._config()
        category = self.category

        if category == "Overview":
            process = self.locator.health()
            health, _ = self._system_health()
            account = f"••••{state.account[-4:]}" if state.connected and state.account else "N/A"
            backend_name = getattr(self.app_ref.backend, "display_name", type(self.app_ref.backend).__name__)
            backend_status = "ERROR" if state.service_error else "CONNECTED" if state.connected else "DISCONNECTED"
            mode = state.trading_mode if not state.service_error else "ERROR"
            return [
                SettingsRow("System health", health),
                SettingsRow("Dashboard", process.status),
                SettingsRow("Dashboard instances", str(process.instance_count)),
                SettingsRow("Dashboard PID", ", ".join(str(pid) for pid in process.pids) or "N/A"),
                SettingsRow("Backend", backend_name),
                SettingsRow("Backend status", backend_status),
                SettingsRow("Account", account),
                SettingsRow("Trading mode", mode),
                SettingsRow("Execution", self._execution_label()),
            ]

        if category == "Gateway & Login":
            host = str(config.get("ib_server_address", "127.0.0.1"))
            port = str(config.get("ib_server_port", "N/A"))
            return [
                SettingsRow("IB endpoint", f"{host}:{port}"),
                SettingsRow("VNC endpoint", "vnc://localhost:5901"),
                SettingsRow("Restart method", "./docker.sh -g", "External action"),
                SettingsRow("MFA", "Operator approval required", "Safety boundary"),
                SettingsRow("Direct IBKR from TUI", "Disabled", "Locked"),
            ]

        if category == "Credentials":
            secrets = Path("~/.config/mmr/secrets.env").expanduser()
            project_env = Path(getattr(self.locator, "project_root", Path.cwd())) / ".env"

            def status(path: Path) -> str:
                if not path.exists():
                    return "Not present"
                try:
                    return f"Present · {path.stat().st_mode & 0o777:04o}"
                except OSError:
                    return "Present · unreadable metadata"

            return [
                SettingsRow("Services secrets", status(secrets)),
                SettingsRow("Gateway environment", status(project_env)),
                SettingsRow("Stored values", "Never displayed", "Locked"),
                SettingsRow("Credential workflow", "./docker.sh -g", "External action"),
            ]

        if category == "Account & Data":
            account = f"••••{state.account[-4:]}" if state.connected and state.account else "N/A"
            quote_states = sorted({str(quote.get("data_type") or "UNKNOWN").upper() for quote in state.quotes.values()})
            return [
                SettingsRow("Selected account", account),
                SettingsRow("Account mode", state.trading_mode if state.connected else "N/A"),
                SettingsRow("State source", "MMR SDK/RPC", "Locked path"),
                SettingsRow("Quote sources", ", ".join(quote_states) or "N/A"),
                SettingsRow("Direct broker session", "Not permitted", "Safety boundary"),
            ]

        if category == "Trading Safety":
            return [
                SettingsRow("Trading mode", str(config.get("trading_mode", state.trading_mode)).upper()),
                SettingsRow("Execution enabled", "Yes" if bool(config.get("execution_enabled", False)) else "No"),
                SettingsRow("IB read-only", "Yes" if bool(config.get("ib_read_only", True)) else "No"),
                SettingsRow("Proposal approval", "Required" if bool(config.get("require_proposal_approval", True)) else "Not required"),
                SettingsRow("Execution state", self._execution_label()),
            ]

        if category == "Risk Limits":
            limits = config.get("risk_limits", {})
            if not isinstance(limits, dict) or not limits:
                return [SettingsRow("Risk limits", "Using backend defaults")]
            return [
                SettingsRow(str(key).replace("_", " ").title(), str(value))
                for key, value in sorted(limits.items())
            ]

        if category == "Watchlist":
            rows = [
                SettingsRow("Watchlist source", self.watchlist_source, "Editable", "choice", "watchlist-source", ("MANUAL", "IBKR")),
                SettingsRow("Persistence", "Saved locally" if not self._pending() else "Unsaved changes"),
            ]
            if self.watchlist_source == "IBKR":
                rows.append(SettingsRow("IBKR watchlist", "Unavailable through current MMR SDK", "Read only"))
                rows.append(SettingsRow("Manual fallback", ", ".join(self.watchlist_symbols) or "Empty", "Preserved"))
                return rows
            for index, symbol in enumerate(self.watchlist_symbols):
                rows.append(
                    SettingsRow(
                        f"{index + 1:>2}  {symbol}",
                        symbol,
                        "Editable",
                        "text",
                        f"watchlist-{index}",
                    )
                )
            if len(self.watchlist_symbols) < MAX_WATCHLIST_SYMBOLS:
                rows.append(SettingsRow("New symbol", "Press N or Enter", "Action", "action", "watchlist-new"))
            return rows

        if category == "Appearance":
            return [
                SettingsRow("Terminal font", "Managed by terminal"),
                SettingsRow("Theme", theme_label(self.theme_name), "Editable", "choice", "theme", theme_labels()),
                SettingsRow("Dense panels", "On" if self.dense else "Off", "Editable", "choice", "dense", ("Off", "On")),
                SettingsRow("Unicode symbols", "On" if self.unicode_symbols else "Off", "Editable", "choice", "unicode", ("Off", "On")),
            ]

        if category == "Diagnostics":
            rows = [SettingsRow("Run all diagnostics", "Press R", "Action", "action", "diagnostics-run")]
            for result in self.diagnostic_results:
                rows.append(
                    SettingsRow(
                        result.title,
                        result.summary,
                        "Fix available" if result.fix else result.status,
                        "action",
                        f"diagnostic-{result.id}",
                    )
                )
            return rows

        return []

    def _summary(self) -> tuple[str, str]:
        health, health_detail = self._system_health()
        summaries = {
            "Overview": (f"SYSTEM HEALTH: {health}", health_detail),
            "Gateway & Login": ("Gateway lifecycle and authentication boundaries.", "Restart and MFA stay explicit operator actions."),
            "Credentials": ("Credential health without secret disclosure.", "Settings never prints passwords, API keys, or full account IDs."),
            "Account & Data": ("Connected account and data source snapshot.", "The TUI remains behind MMR SDK/RPC."),
            "Trading Safety": ("Current execution gates from the live MMR configuration.", "Changes to live trading stay outside this screen."),
            "Risk Limits": ("Active pre-trade risk configuration.", "Risk limits remain backend-owned and read-only here."),
            "Watchlist": ("Prioritized manual watchlist with a maximum of 10 symbols.", "N adds, X removes, Shift+Up/Down reorders, A saves."),
            "Appearance": ("Actual Textual themes and terminal presentation.", "Theme changes preview immediately; A saves and D restores."),
            "Diagnostics": ("Structured doctor checks with confirmation-gated repairs.", "R runs checks. Enter inspects or proposes the selected fix."),
        }
        return summaries[self.category]

    @staticmethod
    def _clip(value: str, width: int) -> str:
        return value if len(value) <= width else value[: max(0, width - 1)] + "…"

    def _render_sections(self) -> Text:
        width = max(32, self.query_one("#settings-sections", Static).size.width or 64)
        name_width = 23
        description_width = max(0, width - name_width - 7)
        text = Text()
        for index, section in enumerate(SECTIONS):
            selected = index == self.section_index
            marker = "›" if selected and self.pane == "sections" else "•" if selected else " "
            pending = "*" if self._pending() and section in {"Watchlist", "Appearance"} else " "
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
                text.append(f"  {self._clip(SECTION_DESCRIPTIONS[section], description_width):<{description_width}}", style="italic dim")
            text.append("\n")
        return text

    def _render_values(self, rows: list[SettingsRow]) -> Text:
        total_width = max(48, self.query_one("#settings-content", Static).size.width or 78)
        name_width = min(28, max(20, total_width // 3))
        access_width = 14
        value_width = min(34, max(14, total_width - name_width - access_width - 5))
        text = Text()
        text.append(f"  {'VARIABLE':<{name_width}} {'VALUE':<{value_width}} {'ACCESS':<{access_width}}\n", style="bold dim")
        for index, row in enumerate(rows):
            active = self.pane == "values" and self.row_index == index
            editing = active and self._edit_row is not None and self._edit_row.key == row.key
            marker = "✎" if editing and self.unicode_symbols else "E" if editing else "›" if active and self.unicode_symbols else ">" if active else " "
            name = self._clip(row.label, name_width)
            if editing:
                value = self._edit_value
                visible_start = max(0, self._edit_cursor - value_width + 1)
                visible = value[visible_start : visible_start + value_width]
                cursor = self._edit_cursor - visible_start
                text.append(f"{marker} {name:<{name_width}} ", style="bold reverse")
                text.append(visible[:cursor], style="bold reverse")
                text.append(visible[cursor : cursor + 1] or " ", style="bold reverse")
                text.append(visible[cursor + 1 :], style="bold reverse")
                used = len(visible[:cursor]) + 1 + len(visible[cursor + 1 :])
                if used < value_width:
                    text.append(" " * (value_width - used), style="reverse")
                text.append(f" {'EDITING':<{access_width}}\n", style="bold reverse")
                continue
            line = (
                f"{marker} {name:<{name_width}} "
                f"{self._clip(row.value, value_width):<{value_width}} "
                f"{self._clip(row.access, access_width):<{access_width}}\n"
            )
            if active:
                text.append(line, style="bold reverse")
            elif row.access in {"Fix available", "Unsaved changes"}:
                text.append(line, style="yellow")
            elif row.kind != "readonly":
                text.append(line)
            else:
                text.append(line, style="dim")
        return text

    def _status(self) -> Text:
        text = Text()
        text.append(f" {self.message} ", style="bold")
        text.append("│", style="magenta")
        if self.editing:
            hints = " Type edit  ←/→ cursor  Enter stage  Esc cancel "
            suggestions = self.store.suggestions(self._edit_value)
            if self._edit_row and self._edit_row.key == "watchlist-new" and suggestions:
                hints += " Suggestions: " + ", ".join(suggestions)
        elif self.pane == "sections":
            hints = " ↑/↓ move  Enter open  Esc close  Ctrl+Q exit "
        else:
            hints = " ↑/↓ move  Enter edit/select  Space select  Esc back  H details "
            if self.category == "Watchlist":
                hints += " N add  X remove  Shift+↑/↓ priority "
            elif self.category == "Diagnostics":
                hints += " R run "
        text.append(hints, style="dim")
        if self._pending():
            text.append("│ A apply  D discard ", style="bold yellow")
        return text

    def render_settings(self) -> None:
        rows = self._rows()
        self.row_index = min(self.row_index, max(0, len(rows) - 1))
        summary, guidance = self._summary()
        state = self.app_ref.state
        runtime = (
            f"{state.trading_mode}  •  "
            f"{'CONNECTED' if state.connected else 'DISCONNECTED'}  •  "
            f"{self._execution_label()}"
        )
        self.query_one("#settings-runtime", Static).update(runtime)
        self.query_one("#settings-sections", Static).update(self._render_sections())
        self.query_one("#settings-breadcrumb", Static).update(f"SETTINGS / {self.category.upper()}")
        self.query_one("#settings-page-title", Label).update(self.category)
        self.query_one("#settings-summary", Static).update(summary)
        self.query_one("#settings-content", Static).update(self._render_values(rows))
        self.query_one("#settings-guidance", Static).update(guidance)
        self.query_one("#settings-statusbar", Static).update(self._status())
        pending = self.query_one("#settings-pending", Static)
        pending.display = self._pending()
        pending.update("PENDING EDITS · A APPLY · D DISCARD" if self._pending() else "")

    def _start_edit(self, row: SettingsRow) -> None:
        self._edit_row = row
        if row.key == "watchlist-new":
            self._edit_value = ""
        elif row.key.startswith("watchlist-"):
            index = int(row.key.split("-", 1)[1])
            self._edit_value = self.watchlist_symbols[index]
        else:
            self._edit_value = row.value
        self._edit_cursor = len(self._edit_value)
        self.message = f"Editing {row.label} inline."
        self.render_settings()

    def _finish_edit(self) -> None:
        self._edit_row = None
        self._edit_value = ""
        self._edit_cursor = 0

    def _commit_edit(self) -> None:
        row = self._edit_row
        if row is None:
            return
        try:
            symbol = self.store.normalize_symbol(self._edit_value)
            if row.key == "watchlist-new":
                if symbol in self.watchlist_symbols:
                    raise UISettingsError(f"{symbol} is already in the watchlist.")
                if len(self.watchlist_symbols) >= MAX_WATCHLIST_SYMBOLS:
                    raise UISettingsError("The watchlist is already at its 10-symbol limit.")
                self.watchlist_symbols.append(symbol)
            elif row.key.startswith("watchlist-"):
                index = int(row.key.split("-", 1)[1])
                if symbol in self.watchlist_symbols and self.watchlist_symbols[index] != symbol:
                    raise UISettingsError(f"{symbol} is already in the watchlist.")
                self.watchlist_symbols[index] = symbol
        except (UISettingsError, ValueError, IndexError) as exc:
            self.message = f"Watchlist edit blocked: {exc}"
            self.render_settings()
            return
        label = row.label
        self._finish_edit()
        self.message = f"{label} staged."
        self.render_settings()

    def _cycle_choice(self, row: SettingsRow) -> None:
        if not row.options:
            return
        current = row.value
        try:
            index = row.options.index(current)
        except ValueError:
            index = -1
        selected = row.options[(index + 1) % len(row.options)]
        if row.key == "watchlist-source":
            self.watchlist_source = selected
        elif row.key == "theme":
            self.theme_name = normalize_theme(selected)
            self.app_ref.theme = self.theme_name
        elif row.key == "dense":
            self.dense = selected == "On"
            self.app_ref.set_class(self.dense, "dense")
        elif row.key == "unicode":
            self.unicode_symbols = selected == "On"
        self.message = f"{row.label} staged: {selected}."
        self.render_settings()

    def _activate(self) -> None:
        rows = self._rows()
        if not rows:
            return
        row = rows[self.row_index]
        if row.kind == "text" or row.key == "watchlist-new":
            self._start_edit(row)
        elif row.kind == "choice":
            self._cycle_choice(row)
        elif row.key == "diagnostics-run":
            self._run_diagnostics()
        elif row.key.startswith("diagnostic-"):
            result_id = row.key.removeprefix("diagnostic-")
            result = next((item for item in self.diagnostic_results if item.id == result_id), None)
            if result is None:
                return
            if result.fix:
                self.app.push_screen(ConfirmFixScreen(result.fix), lambda confirmed: self._apply_fix(result.fix) if confirmed else self._cancel_fix())
            else:
                detail = " · ".join(result.details) if result.details else result.summary
                self.message = f"{result.status}: {detail}"
                self.render_settings()
        else:
            self.message = f"{row.label} is read only."
            self.render_settings()

    def _run_diagnostics(self) -> None:
        self.diagnostic_results = self.doctor.run_all()
        counts = {status: sum(result.status == status for result in self.diagnostic_results) for status in ("PASS", "WARN", "FAIL", "UNKNOWN")}
        self.message = "Diagnostics: " + "  ".join(f"{key} {value}" for key, value in counts.items())
        self.render_settings()

    def _apply_fix(self, plan: FixPlan) -> None:
        success, message = self.doctor.apply_fix(plan)
        self.diagnostic_results = self.doctor.run_all()
        self.message = ("Fixed: " if success else "Fix failed: ") + message
        self.render_settings()

    def _cancel_fix(self) -> None:
        self.message = "Repair cancelled; no changes were made."
        self.render_settings()

    def _apply(self) -> None:
        if not self._pending():
            self.message = "No pending Settings edits."
            self.render_settings()
            return
        if self.watchlist_source == "IBKR":
            self.message = "Apply blocked: the current MMR SDK does not expose broker watchlists."
            self.render_settings()
            return
        settings = UISettings(
            watchlist_source=self.watchlist_source,
            manual_symbols=list(self.watchlist_symbols),
            symbol_history=list(self.store.settings.symbol_history),
            theme=self.theme_name,
            dense=self.dense,
            unicode_symbols=self.unicode_symbols,
        )
        try:
            self.store.settings = settings
            self.store.update_history(self.watchlist_symbols)
            self.store.save(self.store.settings)
        except (OSError, UISettingsError) as exc:
            self.message = f"Settings were not saved: {type(exc).__name__}: {exc}"
            self.render_settings()
            return
        self.app_ref.watchlist = list(self.watchlist_symbols)
        self.app_ref.theme = self.theme_name
        self.app_ref.set_class(self.dense, "dense")
        self._saved_snapshot = self._snapshot()
        self.message = "Watchlist and appearance settings applied."
        self.app_ref.action_refresh()
        self.render_settings()

    def _discard(self) -> None:
        source, symbols, theme, dense, unicode_symbols = self._saved_snapshot
        self.watchlist_source = source
        self.watchlist_symbols = list(symbols)
        self.theme_name = theme
        self.dense = dense
        self.unicode_symbols = unicode_symbols
        self.app_ref.theme = self.theme_name
        self.app_ref.set_class(self.dense, "dense")
        self.message = "Pending Settings edits discarded."
        self.render_settings()

    def _remove_watchlist(self) -> bool:
        if self.category != "Watchlist" or self.watchlist_source != "MANUAL":
            return False
        rows = self._rows()
        row = rows[self.row_index]
        if not row.key.startswith("watchlist-") or row.key in {"watchlist-source", "watchlist-new"}:
            return False
        index = int(row.key.split("-", 1)[1])
        self.watchlist_symbols.pop(index)
        self.row_index = min(self.row_index, len(self._rows()) - 1)
        self.message = "Symbol removed from the staged watchlist."
        self.render_settings()
        return True

    def _move_watchlist(self, target: int) -> bool:
        if self.category != "Watchlist" or self.watchlist_source != "MANUAL":
            return False
        rows = self._rows()
        row = rows[self.row_index]
        if not row.key.startswith("watchlist-") or row.key in {"watchlist-source", "watchlist-new"}:
            return False
        index = int(row.key.split("-", 1)[1])
        target = max(0, min(len(self.watchlist_symbols) - 1, target))
        if target == index:
            return True
        symbol = self.watchlist_symbols.pop(index)
        self.watchlist_symbols.insert(target, symbol)
        self.row_index += target - index
        self.message = f"{symbol} moved to priority {target + 1}."
        self.render_settings()
        return True

    def _handle_edit_key(self, event: events.Key) -> bool:
        key = event.key
        if key == "enter":
            self._commit_edit()
        elif key == "escape":
            self._finish_edit()
            self.message = "Edit cancelled."
            self.render_settings()
        elif key == "left":
            self._edit_cursor = max(0, self._edit_cursor - 1)
            self.render_settings()
        elif key == "right":
            self._edit_cursor = min(len(self._edit_value), self._edit_cursor + 1)
            self.render_settings()
        elif key == "home":
            self._edit_cursor = 0
            self.render_settings()
        elif key == "end":
            self._edit_cursor = len(self._edit_value)
            self.render_settings()
        elif key == "backspace" and self._edit_cursor:
            self._edit_value = self._edit_value[: self._edit_cursor - 1] + self._edit_value[self._edit_cursor :]
            self._edit_cursor -= 1
            self.render_settings()
        elif key == "delete" and self._edit_cursor < len(self._edit_value):
            self._edit_value = self._edit_value[: self._edit_cursor] + self._edit_value[self._edit_cursor + 1 :]
            self.render_settings()
        elif event.is_printable and event.character:
            self._edit_value = self._edit_value[: self._edit_cursor] + event.character + self._edit_value[self._edit_cursor :]
            self._edit_cursor += len(event.character)
            self.render_settings()
        else:
            return False
        return True

    def on_paste(self, event: events.Paste) -> None:
        if self.editing:
            self._edit_value = self._edit_value[: self._edit_cursor] + event.text + self._edit_value[self._edit_cursor :]
            self._edit_cursor += len(event.text)
            self.render_settings()
            event.stop()

    def on_key(self, event: events.Key) -> None:
        if event.key == "ctrl+q":
            self.app.exit()
            event.stop()
            event.prevent_default()
            return
        if self.editing:
            if self._handle_edit_key(event):
                event.stop()
                event.prevent_default()
            return

        key = event.key
        handled = True
        if key in {"up", "k"}:
            if self.pane == "sections":
                self.section_index = max(0, self.section_index - 1)
                self.row_index = 0
            else:
                self.row_index = max(0, self.row_index - 1)
            self.render_settings()
        elif key in {"down", "j"}:
            if self.pane == "sections":
                self.section_index = min(len(SECTIONS) - 1, self.section_index + 1)
                self.row_index = 0
            else:
                self.row_index = min(max(0, len(self._rows()) - 1), self.row_index + 1)
            self.render_settings()
        elif key in {"enter", "right"}:
            if self.pane == "sections":
                self._set_pane("values")
                self.row_index = 0
                self.message = f"{self.category} active."
                self.render_settings()
            else:
                self._activate()
        elif key == "space" and self.pane == "values":
            rows = self._rows()
            if rows and rows[self.row_index].kind == "choice":
                self._cycle_choice(rows[self.row_index])
            else:
                handled = False
        elif key in {"escape", "left"}:
            if self.pane == "values":
                self._set_pane("sections")
                self.message = "Section list active."
                self.render_settings()
            else:
                if self._pending():
                    self._discard()
                self.dismiss(None)
        elif key.lower() == "a":
            self._apply()
        elif key.lower() == "d":
            self._discard()
        elif key.lower() == "r" and self.category == "Diagnostics":
            self._run_diagnostics()
        elif key.lower() == "n" and self.category == "Watchlist":
            for index, row in enumerate(self._rows()):
                if row.key == "watchlist-new":
                    self.row_index = index
                    self._start_edit(row)
                    break
            else:
                self.message = "The manual watchlist already contains 10 symbols."
                self.render_settings()
        elif key.lower() == "x" or key == "delete":
            handled = self._remove_watchlist()
        elif key == "shift+up":
            handled = self._move_watchlist(max(0, self.row_index - 3))
        elif key == "shift+down":
            handled = self._move_watchlist(min(len(self.watchlist_symbols) - 1, self.row_index - 1))
        elif key == "home" and self.category == "Watchlist":
            handled = self._move_watchlist(0)
        elif key == "end" and self.category == "Watchlist":
            handled = self._move_watchlist(len(self.watchlist_symbols) - 1)
        elif key.lower() == "h" and self.pane == "values":
            rows = self._rows()
            row = rows[self.row_index] if rows else None
            if row:
                self.message = f"{row.label}: {row.value} · {row.access}"
                self.render_settings()
        else:
            handled = False

        if handled:
            event.stop()
            event.prevent_default()
