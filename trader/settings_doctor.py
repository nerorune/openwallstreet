"""Structured diagnostics and narrowly-scoped confirmed repairs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import os
import stat

from trader.settings_health import DashboardProcessLocator, DuplicateProcessPlan


@dataclass(frozen=True)
class FixPlan:
    fix_id: str
    title: str
    summary: str
    targets: tuple[str, ...]
    reversible: str
    payload: object | None = None

    def confirmation_text(self) -> str:
        target_text = "\n".join(f"  • {target}" for target in self.targets) or "  • None"
        return (
            f"{self.title}\n\n{self.summary}\n\nAffected targets:\n{target_text}\n\n"
            f"Reversibility: {self.reversible}"
        )


@dataclass(frozen=True)
class DiagnosticResult:
    id: str
    title: str
    status: str
    summary: str
    details: tuple[str, ...] = field(default_factory=tuple)
    fix: FixPlan | None = None


class DiagnosticsDoctor:
    """Diagnose the production MMR-backed terminal without bypassing MMR."""

    def __init__(self, app: Any, locator: DashboardProcessLocator) -> None:
        self.app = app
        self.locator = locator

    @property
    def config(self) -> dict[str, Any]:
        try:
            from trader.container import Container

            return dict(Container.instance().config())
        except Exception:
            return {}

    @property
    def config_path(self) -> Path:
        try:
            from trader.container import Container

            return Path(Container.instance().config_file).expanduser()
        except Exception:
            return Path("~/.config/mmr/trader.yaml").expanduser()

    @property
    def secrets_path(self) -> Path:
        return Path("~/.config/mmr/secrets.env").expanduser()

    def run_all(self) -> list[DiagnosticResult]:
        return [
            self.check_dashboard_processes(),
            self.check_backend(),
            self.check_account(),
            self.check_execution(),
            self.check_config(),
            self.check_secrets_permissions(),
            self.check_logfile(),
        ]

    def check_dashboard_processes(self) -> DiagnosticResult:
        health = self.locator.health()
        details = tuple(
            f"PID {process.pid} · {process.launch_mechanism} · {int(process.uptime_seconds)}s · {process.command_text}"
            for process in health.processes
        )
        fix = None
        if health.instance_count > 1:
            plan = self.locator.duplicate_plan()
            if plan:
                fix = FixPlan(
                    fix_id="terminate-duplicate-dashboards",
                    title="Stop duplicate OpenWallStreet dashboards",
                    summary="Terminate only the confirmed duplicate TUI processes and keep this dashboard running.",
                    targets=tuple(f"PID {pid}: {command}" for pid, command in zip(plan.pids, plan.commands, strict=True)),
                    reversible="The stopped processes must be relaunched manually with `uv run mmr tui`.",
                    payload=plan,
                )
        status = "PASS" if health.status == "HEALTHY" else "FAIL" if health.status in {"STOPPED", "DEGRADED"} else "UNKNOWN"
        return DiagnosticResult(
            id="dashboard-processes",
            title="Dashboard processes",
            status=status,
            summary=health.detail,
            details=details or (f"Start command: {health.helper_command}",),
            fix=fix,
        )

    def check_backend(self) -> DiagnosticResult:
        state = self.app.state
        backend_name = getattr(self.app.backend, "display_name", type(self.app.backend).__name__)
        if state.service_error:
            return DiagnosticResult(
                id="backend",
                title="Backend connection",
                status="FAIL",
                summary=f"{backend_name} reported an error.",
                details=(state.service_error,),
            )
        if not state.connected:
            return DiagnosticResult(
                id="backend",
                title="Backend connection",
                status="WARN",
                summary=f"{backend_name} is disconnected.",
                details=("The TUI uses MMR SDK/RPC only; it does not open a second IBKR connection.",),
            )
        return DiagnosticResult(
            id="backend",
            title="Backend connection",
            status="PASS",
            summary=f"{backend_name} is connected.",
            details=("MMR SDK/RPC boundary is active.",),
        )

    def check_account(self) -> DiagnosticResult:
        state = self.app.state
        if getattr(self.app.backend, "is_demo", False):
            return DiagnosticResult("account", "Account", "PASS", "Demo mode has no broker account.")
        if not state.connected or not state.account:
            return DiagnosticResult("account", "Account", "WARN", "No connected broker account is available.")
        return DiagnosticResult(
            "account",
            "Account",
            "PASS",
            f"Connected account ends in {state.account[-4:]}",
            ("The complete account identifier is never displayed by Settings.",),
        )

    def check_execution(self) -> DiagnosticResult:
        state = self.app.state
        config = self.config
        read_only = bool(config.get("ib_read_only", True))
        approval = bool(config.get("require_proposal_approval", True))
        details = (
            f"Trading mode: {state.trading_mode}",
            f"Execution enabled: {state.execution_enabled}",
            f"IB read-only: {read_only}",
            f"Proposal approval required: {approval}",
        )
        if state.trading_mode == "LIVE" and state.execution_enabled and not read_only:
            return DiagnosticResult("execution", "Execution safety", "WARN", "LIVE execution is enabled.", details)
        if not state.execution_enabled or read_only:
            return DiagnosticResult("execution", "Execution safety", "PASS", "Execution is locked or read-only.", details)
        return DiagnosticResult("execution", "Execution safety", "PASS", "Paper execution is enabled through MMR.", details)

    def check_config(self) -> DiagnosticResult:
        path = self.config_path
        if not path.exists():
            return DiagnosticResult("config", "Trader configuration", "FAIL", f"Missing configuration: {path}")
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
            readable = os.access(path, os.R_OK)
        except OSError as exc:
            return DiagnosticResult("config", "Trader configuration", "UNKNOWN", f"Unable to inspect config: {type(exc).__name__}")
        status = "PASS" if readable else "FAIL"
        return DiagnosticResult(
            "config",
            "Trader configuration",
            status,
            "Configuration is readable." if readable else "Configuration is not readable.",
            (str(path), f"Permissions: {mode:04o}"),
        )

    def check_secrets_permissions(self) -> DiagnosticResult:
        path = self.secrets_path
        if not path.exists():
            return DiagnosticResult(
                "secrets",
                "Secrets file",
                "PASS",
                "No services-only secrets file is present.",
                (str(path),),
            )
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError as exc:
            return DiagnosticResult("secrets", "Secrets file", "UNKNOWN", f"Unable to inspect secrets: {type(exc).__name__}")
        if mode & 0o077:
            fix = FixPlan(
                fix_id="secure-secrets-file",
                title="Restrict MMR secrets file permissions",
                summary="Change the existing MMR services-only secrets file to owner read/write (0600).",
                targets=(str(path), f"Current permissions: {mode:04o}", "New permissions: 0600"),
                reversible=f"Restore the previous mode manually with `chmod {mode:04o} {path}`.",
                payload=mode,
            )
            return DiagnosticResult(
                "secrets",
                "Secrets file",
                "FAIL",
                f"Secrets file permissions are too broad: {mode:04o}.",
                (str(path),),
                fix,
            )
        return DiagnosticResult("secrets", "Secrets file", "PASS", "Secrets file permissions are restricted.", (str(path), f"Permissions: {mode:04o}"))

    def check_logfile(self) -> DiagnosticResult:
        raw = str(self.config.get("logfile", "~/.local/share/mmr/logs/trader.log"))
        path = Path(raw).expanduser()
        if not path.exists():
            return DiagnosticResult("logfile", "Trader log", "WARN", "Trader log does not exist yet.", (str(path),))
        try:
            size = path.stat().st_size
            readable = os.access(path, os.R_OK)
        except OSError as exc:
            return DiagnosticResult("logfile", "Trader log", "UNKNOWN", f"Unable to inspect log: {type(exc).__name__}")
        return DiagnosticResult(
            "logfile",
            "Trader log",
            "PASS" if readable else "FAIL",
            "Trader log is readable." if readable else "Trader log is not readable.",
            (str(path), f"Size: {size:,} bytes"),
        )

    def apply_fix(self, plan: FixPlan) -> tuple[bool, str]:
        if plan.fix_id == "terminate-duplicate-dashboards" and isinstance(plan.payload, DuplicateProcessPlan):
            return self.locator.terminate_confirmed_duplicates(plan.payload)
        if plan.fix_id == "secure-secrets-file":
            path = self.secrets_path
            if not path.exists():
                return False, "Secrets file disappeared after confirmation; no change was made."
            try:
                os.chmod(path, 0o600)
            except OSError as exc:
                return False, f"Unable to change permissions: {type(exc).__name__}"
            return True, f"Restricted {path} to 0600."
        return False, f"Unsupported fix: {plan.fix_id}"
