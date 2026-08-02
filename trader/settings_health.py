"""Process and runtime health helpers for the OpenWallStreet Textual terminal."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import os
import time

import psutil


@dataclass(frozen=True)
class DashboardProcess:
    pid: int
    command: tuple[str, ...]
    cwd: str
    create_time: float
    uptime_seconds: float
    launch_mechanism: str

    @property
    def command_text(self) -> str:
        return " ".join(self.command)


@dataclass(frozen=True)
class DashboardHealth:
    status: str
    processes: tuple[DashboardProcess, ...] = field(default_factory=tuple)
    helper_command: str = "uv run mmr tui"
    detail: str = ""

    @property
    def instance_count(self) -> int:
        return len(self.processes)

    @property
    def pids(self) -> tuple[int, ...]:
        return tuple(process.pid for process in self.processes)


@dataclass(frozen=True)
class DuplicateProcessPlan:
    pids: tuple[int, ...]
    commands: tuple[str, ...]
    current_pid: int


class DashboardProcessLocator:
    """Identify only the OpenWallStreet/MMR Textual command surface.

    Detection uses tokenized command lines plus the known project root. It does
    not use broad substring matches such as ``pkill python``.
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        current_pid: int | None = None,
        process_iter: Callable[..., Iterable[Any]] = psutil.process_iter,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.current_pid = int(current_pid or os.getpid())
        self.process_iter = process_iter
        self.now = now

    @staticmethod
    def _is_tui_command(tokens: tuple[str, ...]) -> tuple[bool, str]:
        if not tokens:
            return False, ""
        lowered = tuple(token.lower() for token in tokens)
        basenames = tuple(Path(token).name.lower() for token in tokens)

        for index, base in enumerate(basenames):
            if base == "mmr" and "tui" in lowered[index + 1 :]:
                return True, "mmr CLI"
        if "-m" in lowered and "trader.mmr_cli" in lowered and "tui" in lowered:
            return True, "python module"
        if any(token.endswith("trader/tui.py") or token.endswith("trader\\tui.py") for token in lowered):
            return True, "python script"
        return False, ""

    def _same_project(self, cwd: str, tokens: tuple[str, ...]) -> bool:
        try:
            if cwd and Path(cwd).resolve() == self.project_root:
                return True
        except OSError:
            pass
        root_text = str(self.project_root)
        return any(root_text in token for token in tokens)

    def discover(self, *, include_current: bool = True) -> list[DashboardProcess]:
        found: dict[int, DashboardProcess] = {}
        for process in self.process_iter(["pid", "cmdline", "create_time", "cwd"]):
            try:
                info = process.info
                pid = int(info["pid"])
                tokens = tuple(str(token) for token in (info.get("cmdline") or ()))
                cwd = str(info.get("cwd") or "")
                matched, mechanism = self._is_tui_command(tokens)
                if not matched or not self._same_project(cwd, tokens):
                    continue
                created = float(info.get("create_time") or 0.0)
                found[pid] = DashboardProcess(
                    pid=pid,
                    command=tokens,
                    cwd=cwd,
                    create_time=created,
                    uptime_seconds=max(0.0, self.now() - created),
                    launch_mechanism=mechanism,
                )
            except (KeyError, TypeError, ValueError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if include_current and self.current_pid not in found:
            try:
                current = psutil.Process(self.current_pid)
                tokens = tuple(current.cmdline())
                cwd = current.cwd()
                created = current.create_time()
                found[self.current_pid] = DashboardProcess(
                    pid=self.current_pid,
                    command=tokens,
                    cwd=cwd,
                    create_time=created,
                    uptime_seconds=max(0.0, self.now() - created),
                    launch_mechanism="current Textual process",
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass
        return sorted(found.values(), key=lambda process: (process.create_time, process.pid))

    def health(self) -> DashboardHealth:
        try:
            processes = tuple(self.discover())
        except Exception as exc:
            return DashboardHealth(status="UNKNOWN", detail=f"Process inspection failed: {type(exc).__name__}")
        if not processes:
            return DashboardHealth(status="STOPPED", detail="No OpenWallStreet TUI process was identified.")
        if len(processes) == 1:
            return DashboardHealth(status="HEALTHY", processes=processes, detail="Exactly one dashboard is running.")
        return DashboardHealth(
            status="DEGRADED",
            processes=processes,
            detail=f"{len(processes)} dashboard processes are running.",
        )

    def duplicate_plan(self) -> DuplicateProcessPlan | None:
        processes = self.discover()
        duplicates = [process for process in processes if process.pid != self.current_pid]
        if not duplicates:
            return None
        return DuplicateProcessPlan(
            pids=tuple(process.pid for process in duplicates),
            commands=tuple(process.command_text for process in duplicates),
            current_pid=self.current_pid,
        )

    def terminate_confirmed_duplicates(self, plan: DuplicateProcessPlan) -> tuple[bool, str]:
        if plan.current_pid != self.current_pid or self.current_pid in plan.pids:
            return False, "Refused an invalid process-repair plan."
        current = {process.pid: process for process in self.discover()}
        for pid, expected_command in zip(plan.pids, plan.commands, strict=True):
            process = current.get(pid)
            if process is None or process.command_text != expected_command:
                return False, f"PID {pid} changed after confirmation; nothing was terminated."
        failures: list[str] = []
        for pid in plan.pids:
            try:
                process = psutil.Process(pid)
                process.terminate()
                process.wait(timeout=3)
            except psutil.TimeoutExpired:
                failures.append(f"PID {pid} did not exit within 3 seconds")
            except psutil.NoSuchProcess:
                continue
            except (psutil.AccessDenied, OSError) as exc:
                failures.append(f"PID {pid}: {type(exc).__name__}")
        if failures:
            return False, "; ".join(failures)
        remaining = self.discover()
        if len(remaining) == 1 and remaining[0].pid == self.current_pid:
            return True, "Duplicate dashboards stopped; the current dashboard remains running."
        return False, f"Repair incomplete: {len(remaining)} dashboard processes remain."
