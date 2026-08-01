"""Textual terminal client for MMR.

The TUI deliberately talks to MMR's public SDK only.  It never imports
``ib_async`` or reaches through the RPC API to an IB object, so its order and
proposal actions retain MMR's server-side approval, risk, account-pinning and
audit boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any, Callable

import math
import pandas as pd
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Label, Static


DEFAULT_WATCHLIST = (
    "QQQ SPY AAPL MSFT NVDA AMZN META GOOGL AVGO AMD PLTR RGTI IONQ QBTS APLD"
).split()
QQQ_COMPONENTS = ("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "AMD")


def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _money(value: Any) -> str:
    value = _number(value)
    return "N/A" if value is None else f"${value:,.2f}"


def _price(value: Any) -> str:
    value = _number(value)
    return "N/A" if value is None else f"{value:,.2f}"


def _masked_account(account: str) -> str:
    return "Not selected" if not account else f"***{account[-4:]}"


def _data_state(tick: dict[str, Any], now: datetime | None = None) -> str:
    """Classify data honestly; missing or unparseable time is never 'live'."""
    if not any(_number(tick.get(k)) is not None for k in ("bid", "ask", "last")):
        return "UNAVAILABLE"
    stamp = tick.get("time")
    if isinstance(stamp, datetime):
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        if age > 10:
            return "STALE"
    return str(tick.get("data_type") or "LIVE").upper()


@dataclass
class TerminalState:
    connected: bool = False
    trading_mode: str = "PAPER"
    execution_enabled: bool = False
    account: str = ""
    account_values: dict[str, Any] = field(default_factory=dict)
    positions: pd.DataFrame = field(default_factory=pd.DataFrame)
    orders: pd.DataFrame = field(default_factory=pd.DataFrame)
    proposals: pd.DataFrame = field(default_factory=pd.DataFrame)
    quotes: dict[str, dict[str, Any]] = field(default_factory=dict)
    activity: list[str] = field(default_factory=list)
    service_error: str = ""

    def note(self, message: str) -> None:
        stamped = f"{datetime.now().strftime('%H:%M:%S')} {message}"
        self.activity = (self.activity + [stamped])[-8:]


class DemoBackend:
    """Deterministic, non-broker demo used for TUI tests and training."""

    is_demo = True

    def __init__(self) -> None:
        self.rng = Random(9600)
        self.tick = 0
        self.base = {symbol: 90.0 + i * 13.7 for i, symbol in enumerate(DEFAULT_WATCHLIST)}

    def refresh(self, symbols: list[str]) -> TerminalState:
        self.tick += 1
        state = TerminalState(connected=True, trading_mode="PAPER", execution_enabled=False,
                              account="DU1234567")
        state.account_values = {
            "NetLiquidation": {"value": 100_000.0, "currency": "USD"},
            "TotalCashValue": {"value": 74_250.0, "currency": "USD"},
            "AvailableFunds": {"value": 72_000.0, "currency": "USD"},
            "BuyingPower": {"value": 144_000.0, "currency": "USD"},
        }
        now = datetime.now(timezone.utc)
        for symbol in symbols:
            base = self.base.get(symbol, 100.0)
            last = base * (1 + math.sin(self.tick / 4 + len(symbol)) * .012)
            spread = max(.01, last * .0008)
            state.quotes[symbol] = {
                "symbol": symbol, "bid": last - spread / 2, "ask": last + spread / 2,
                "last": last, "open": base, "previous_close": base * .995,
                "volume": 1_250_000 + self.tick * 1000, "time": now, "data_type": "DEMO",
            }
        state.positions = pd.DataFrame([
            {"symbol": "QQQ", "position": 10, "avgCost": 500.00, "mktPrice": 505.00,
             "marketValue": 5050.0, "unrealizedPNL": 50.0, "dailyPNL": 12.0, "currency": "USD"},
        ])
        state.orders = pd.DataFrame([
            {"orderId": 9001, "symbol": "AAPL", "action": "BUY", "orderType": "LMT",
             "quantity": 1, "lmtPrice": 200.0, "status": "Submitted", "filled": 0},
        ])
        state.proposals = pd.DataFrame([
            {"id": 42, "symbol": "AMD", "action": "BUY", "size": "2 sh", "order": "LMT @120",
             "conf": "70%", "status": "PENDING", "reasoning": "Demo proposal; no broker action."},
        ])
        state.note("Demo update: deterministic simulated data (not IBKR).")
        return state

    def reject(self, proposal_id: int, reason: str) -> bool:
        return proposal_id == 42

    def approve(self, proposal_id: int) -> str:
        return "Demo mode blocks execution; no order was sent."


class MMRBackend:
    """Thin adapter around the supported MMR Python SDK."""

    is_demo = False

    def __init__(self) -> None:
        from trader.sdk import MMR
        from trader.container import Container
        self.mmr = MMR()
        self._connected = False
        config = Container.instance().config()
        self.trading_mode = str(config.get("trading_mode", "paper")).upper()
        self.execution_enabled = bool(config.get("execution_enabled", False))

    def refresh(self, symbols: list[str]) -> TerminalState:
        if not self._connected:
            self.mmr.connect()
            self._connected = True
        state = TerminalState(trading_mode=self.trading_mode,
                              execution_enabled=self.execution_enabled)
        status = self.mmr.status()
        state.connected = bool(status.get("connected") and status.get("ib_upstream_connected", True))
        state.service_error = str(status.get("ib_upstream_error", ""))
        state.account = str(status.get("account", ""))
        state.account_values = status.get("account_values", {}) or {}
        state.positions = self.mmr.portfolio()
        state.orders = self.mmr.orders()
        state.proposals = self.mmr.proposals(status=None)
        try:
            state.quotes = {q.get("symbol", symbols[i]): q for i, q in
                            enumerate(self.mmr.snapshot_batch(symbols))}
        except Exception as exc:
            state.note(f"Quotes unavailable: {type(exc).__name__}: {exc}")
        state.note("MMR refresh completed through local SDK/RPC.")
        return state

    def reject(self, proposal_id: int, reason: str) -> bool:
        return self.mmr.reject(proposal_id, reason)

    def approve(self, proposal_id: int) -> str:
        result = self.mmr.approve(proposal_id)
        if result.is_success():
            return f"Proposal #{proposal_id} approved; MMR submitted the paper order."
        return f"MMR refused proposal #{proposal_id}: {result.error or 'unknown error'}"

    def close(self) -> None:
        self.mmr.close()


class ConfirmScreen(ModalScreen[bool]):
    """A keyboard-only confirmation gate for proposal decisions."""

    BINDINGS = [("y", "confirm", "Confirm"), ("n", "cancel", "Cancel"), ("escape", "cancel", "Cancel")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        yield Container(Static(self.message, id="confirm-message"),
                        Static("Press Y to continue or N/Esc to cancel.", id="confirm-help"), id="confirm")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class OrderPreviewScreen(ModalScreen[None]):
    """Paper-only order preview. It creates a proposal; approval remains separate."""

    BINDINGS = [("escape", "dismiss_screen", "Back")]

    def __init__(self, app_ref: "MMRTerminal") -> None:
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Paper order preview → proposal (no order is submitted here)"),
            Input("QQQ", placeholder="Symbol", id="ticket-symbol"),
            Input("1", placeholder="Quantity", id="ticket-quantity"),
            Input("", placeholder="Limit price (required; market orders disabled)", id="ticket-limit"),
            Static("Preview requires a qualified MMR/IBKR contract, fresh quote and backend risk gate.", id="ticket-result"),
            Static("Enter: preview  •  Esc: cancel", id="confirm-help"), id="ticket")

    def on_input_submitted(self) -> None:
        symbol = self.query_one("#ticket-symbol", Input).value.strip().upper()
        qty = _number(self.query_one("#ticket-quantity", Input).value)
        limit = _number(self.query_one("#ticket-limit", Input).value)
        result = self.query_one("#ticket-result", Static)
        if not symbol or qty is None or qty <= 0 or limit is None or limit <= 0:
            result.update("Blocked: symbol, positive quantity and a positive limit price are required.")
            return
        quote = self.app_ref.state.quotes.get(symbol, {})
        data_state = _data_state(quote)
        if data_state in {"STALE", "UNAVAILABLE"}:
            result.update(f"Blocked: {symbol} quote is {data_state}; refresh before proposing.")
            return
        notional = qty * limit
        if notional > 1000:
            result.update(f"Blocked by local preview cap: ${notional:,.2f} > $1,000.00.")
            return
        result.update(
            f"Preview: PAPER BUY {qty:g} {symbol} LMT @{limit:.2f}; est. ${notional:,.2f}; "
            f"bid {_price(quote.get('bid'))} / ask {_price(quote.get('ask'))}; {data_state}.\n"
            "Create the proposal with P, then approve it separately with A after review."
        )

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


class MMRTerminal(App):
    """Responsive, paper-branded trading terminal backed by MMR."""

    CSS = """
    Screen { background: $surface; }
    #paper { color: $warning; text-style: bold; }
    #topline, #activity, #qqq, #account { border: round $primary; padding: 0 1; }
    #main { height: 1fr; grid-size: 2; grid-gutter: 1; }
    DataTable { height: 1fr; min-height: 8; }
    #confirm, #ticket { width: 70; max-width: 95%; height: auto; border: thick $primary; background: $panel; padding: 1 2; }
    #confirm-help { color: $text-muted; margin-top: 1; }
    .compact #main { grid-size: 1; }
    .compact #qqq { display: none; }
    .compact DataTable { min-height: 6; }
    """
    BINDINGS = [
        ("r", "refresh", "Refresh"), ("o", "order_preview", "Order preview"),
        ("a", "approve_selected", "Approve proposal"), ("x", "reject_selected", "Reject proposal"),
        ("d", "doctor", "Doctor"), ("q", "quit", "Quit"),
    ]

    def __init__(self, demo: bool = False, watchlist: list[str] | None = None) -> None:
        super().__init__()
        self.backend = DemoBackend() if demo else MMRBackend()
        self.watchlist: list[str] = list(watchlist or DEFAULT_WATCHLIST)
        self.state = TerminalState()
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("MMR IBKR TUI  |  PAPER ONLY  |  Connecting…", id="topline")
        with Grid(id="main"):
            with Vertical():
                yield DataTable(id="watchlist")
                yield DataTable(id="positions")
            with Vertical():
                yield Static("Account loading…", id="account")
                yield DataTable(id="orders")
                yield DataTable(id="proposals")
        yield Static("QQQ monitor loading…", id="qqq")
        yield Static("Starting…", id="activity")
        yield Footer()

    def on_mount(self) -> None:
        self._init_tables()
        self.action_refresh()
        self.set_interval(5, self.action_refresh)

    def on_resize(self, event) -> None:
        """Use a single-column fallback for SSH/mobile-width terminals."""
        self.set_class(event.size.width < 80, "compact")

    def _init_tables(self) -> None:
        columns = {
            "watchlist": ("Symbol", "Bid", "Ask", "Last", "Chg%", "State"),
            "positions": ("Symbol", "Qty", "Cost", "Value", "Unrl P&L"),
            "orders": ("ID", "Symbol", "Side", "Type", "Qty", "Status"),
            "proposals": ("ID", "Symbol", "Side", "Size", "Order", "State"),
        }
        for ident, names in columns.items():
            table = self.query_one(f"#{ident}", DataTable)
            table.cursor_type = "row"
            table.add_columns(*names)

    def action_refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.run_worker(self._refresh_worker, thread=True, exclusive=True)

    def _refresh_worker(self) -> None:
        try:
            state = self.backend.refresh(self.watchlist)
        except Exception as exc:
            state = self.state
            state.connected = False
            state.service_error = f"{type(exc).__name__}: {exc}"
            state.note(f"Refresh failed: {state.service_error}")
        self.call_from_thread(self._apply_state, state)

    def _apply_state(self, state: TerminalState) -> None:
        self.state = state
        self._busy = False
        self.query_one("#topline", Static).update(
            f"MMR IBKR TUI  |  {state.trading_mode} DATA  |  EXECUTION "
            f"{'ENABLED' if state.execution_enabled else 'LOCKED'}  |  "
            f"{'CONNECTED' if state.connected else 'DISCONNECTED'}"
            f"  |  Account {_masked_account(state.account)}"
        )
        values = state.account_values
        def account_value(name: str) -> Any:
            value = values.get(name, {})
            return value.get("value") if isinstance(value, dict) else value
        self.query_one("#account", Static).update(
            "Account  |  PAPER\n"
            f"Net Liq {_money(account_value('NetLiquidation'))}  Cash {_money(account_value('TotalCashValue'))}\n"
            f"Available {_money(account_value('AvailableFunds'))}  Buying Power {_money(account_value('BuyingPower'))}\n"
            f"Service: {'OK' if not state.service_error else state.service_error}"
        )
        self._fill_watchlist(); self._fill_positions(); self._fill_orders(); self._fill_proposals(); self._fill_qqq()
        self.query_one("#activity", Static).update("\n".join(state.activity) or "No activity yet.")

    def _replace_rows(self, ident: str, rows: list[tuple[Any, ...]]) -> None:
        table = self.query_one(f"#{ident}", DataTable)
        table.clear(columns=False)
        for row in rows:
            table.add_row(*(str(v) for v in row))

    def _fill_watchlist(self) -> None:
        rows = []
        for symbol in self.watchlist:
            q = self.state.quotes.get(symbol, {})
            last, prev = _number(q.get("last")), _number(q.get("previous_close"))
            change = (last - prev) / prev * 100 if last is not None and prev else None
            rows.append((symbol, _price(q.get("bid")), _price(q.get("ask")), _price(last),
                         "N/A" if change is None else f"{change:+.2f}%", _data_state(q)))
        self._replace_rows("watchlist", rows)

    def _fill_positions(self) -> None:
        df = self.state.positions
        rows = [] if df.empty else [(
            r.get("symbol", ""), r.get("position", ""), _price(r.get("avgCost")),
            _money(r.get("marketValue")), _money(r.get("unrealizedPNL")),
        ) for _, r in df.iterrows()]
        self._replace_rows("positions", rows or [("No positions", "", "", "", "")])

    def _fill_orders(self) -> None:
        df = self.state.orders
        rows = [] if df.empty else [(
            r.get("orderId", ""), r.get("symbol", ""), r.get("action", ""), r.get("orderType", ""),
            r.get("quantity", r.get("totalQuantity", "")), r.get("status", ""),
        ) for _, r in df.iterrows()]
        self._replace_rows("orders", rows or [("No open orders", "", "", "", "", "")])

    def _fill_proposals(self) -> None:
        df = self.state.proposals
        rows = [] if df.empty else [(
            r.get("id", ""), r.get("symbol", ""), r.get("action", ""), r.get("size", ""),
            r.get("order", ""), r.get("status", ""),
        ) for _, r in df.iterrows()]
        self._replace_rows("proposals", rows or [("No proposals", "", "", "", "", "")])

    def _fill_qqq(self) -> None:
        values = []
        for symbol in QQQ_COMPONENTS:
            q = self.state.quotes.get(symbol, {})
            last, opening = _number(q.get("last")), _number(q.get("open"))
            change = (last - opening) / opening * 100 if last is not None and opening else None
            values.append(change)
        known = [v for v in values if v is not None]
        up = sum(v > 0 for v in known); down = sum(v < 0 for v in known)
        qqq = self.state.quotes.get("QQQ", {})
        self.query_one("#qqq", Static).update(
            f"QQQ monitor (unweighted breadth; informational)  QQQ {_price(qqq.get('last'))}  "
            f"Components: {up} above open / {down} below open / {len(QQQ_COMPONENTS)-len(known)} unavailable  "
            f"Data: {_data_state(qqq)}"
        )

    def _selected_proposal_id(self) -> int | None:
        table = self.query_one("#proposals", DataTable)
        if table.cursor_row is None or self.state.proposals.empty:
            return None
        try:
            return int(self.state.proposals.iloc[table.cursor_row].get("id"))
        except (IndexError, TypeError, ValueError):
            return None

    def action_order_preview(self) -> None:
        self.push_screen(OrderPreviewScreen(self))

    def action_approve_selected(self) -> None:
        if not self.state.execution_enabled:
            self.state.note("Execution is locked in MMR; approval cannot send an IBKR order.")
            self._apply_state(self.state)
            return
        proposal_id = self._selected_proposal_id()
        if proposal_id is None:
            self.state.note("Select a proposal row first."); self._apply_state(self.state); return
        self.push_screen(ConfirmScreen(f"Approve proposal #{proposal_id}? MMR will validate and may transmit a PAPER order."),
                         lambda yes: self._decision(proposal_id, True) if yes else None)

    def action_reject_selected(self) -> None:
        proposal_id = self._selected_proposal_id()
        if proposal_id is None:
            self.state.note("Select a proposal row first."); self._apply_state(self.state); return
        self.push_screen(ConfirmScreen(f"Reject proposal #{proposal_id}? This is permanent."),
                         lambda yes: self._decision(proposal_id, False) if yes else None)

    def _decision(self, proposal_id: int, approve: bool) -> None:
        def work() -> None:
            try:
                result = self.backend.approve(proposal_id) if approve else (
                    "Proposal rejected." if self.backend.reject(proposal_id, "Rejected in MMR TUI") else "Rejection refused.")
                self.state.note(result)
            except Exception as exc:
                self.state.note(f"Decision failed: {type(exc).__name__}: {exc}")
            self.call_from_thread(self.action_refresh)
        self.run_worker(work, thread=True)

    def action_doctor(self) -> None:
        mode = "demo (no broker)" if self.backend.is_demo else "MMR SDK → localhost RPC"
        self.state.note(f"Doctor: {mode}; PAPER branding active; no direct IBKR API path in TUI.")
        self._apply_state(self.state)

    def on_unmount(self) -> None:
        close = getattr(self.backend, "close", None)
        if close:
            close()


def run_tui(demo: bool = False, watchlist: list[str] | None = None) -> None:
    MMRTerminal(demo=demo, watchlist=watchlist).run()
