"""Persistent, local-only UI preferences for the OpenWallStreet terminal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json
import os
import re
import tempfile


SCHEMA_VERSION = 1
MAX_WATCHLIST_SYMBOLS = 10
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


class UISettingsError(ValueError):
    """Raised when persisted UI configuration is malformed or unsafe."""


@dataclass
class SymbolHistoryEntry:
    symbol: str
    last_used: str
    usage_count: int = 1


@dataclass
class UISettings:
    schema_version: int = SCHEMA_VERSION
    watchlist_source: str = "MANUAL"
    manual_symbols: list[str] = field(default_factory=list)
    symbol_history: list[SymbolHistoryEntry] = field(default_factory=list)
    theme: str = "openwallstreet-dark"
    dense: bool = False
    unicode_symbols: bool = True


class UISettingsStore:
    """Atomic JSON persistence under the existing ``~/.config/mmr`` boundary."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or "~/.config/mmr/ui.json").expanduser()
        self.backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        self.load_warning = ""
        self.settings = self.load()

    @staticmethod
    def normalize_symbol(raw: str) -> str:
        symbol = raw.strip().upper()
        if not symbol:
            raise UISettingsError("Symbol cannot be empty.")
        if not _SYMBOL_RE.fullmatch(symbol):
            raise UISettingsError(
                "Use 1–15 letters, numbers, dots, or hyphens; the first character must be alphanumeric."
            )
        return symbol

    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in values:
            symbol = cls.normalize_symbol(raw)
            if symbol in normalized:
                raise UISettingsError(f"{symbol} is already in the watchlist.")
            normalized.append(symbol)
        if len(normalized) > MAX_WATCHLIST_SYMBOLS:
            raise UISettingsError(f"A manual watchlist may contain at most {MAX_WATCHLIST_SYMBOLS} symbols.")
        return normalized

    @staticmethod
    def _decode(payload: dict[str, Any]) -> UISettings:
        version = int(payload.get("schema_version", 0))
        if version != SCHEMA_VERSION:
            raise UISettingsError(f"Unsupported UI settings schema: {version}.")
        source = str(payload.get("watchlist_source", "MANUAL")).upper()
        if source not in {"MANUAL", "IBKR"}:
            raise UISettingsError(f"Unknown watchlist source: {source}.")
        symbols = UISettingsStore.normalize_symbols(list(payload.get("manual_symbols", [])))
        history: list[SymbolHistoryEntry] = []
        for item in payload.get("symbol_history", []):
            if not isinstance(item, dict):
                continue
            try:
                history.append(
                    SymbolHistoryEntry(
                        symbol=UISettingsStore.normalize_symbol(str(item.get("symbol", ""))),
                        last_used=str(item.get("last_used", "")),
                        usage_count=max(1, int(item.get("usage_count", 1))),
                    )
                )
            except (UISettingsError, TypeError, ValueError):
                continue
        history.sort(key=lambda entry: (entry.usage_count, entry.last_used), reverse=True)
        return UISettings(
            watchlist_source=source,
            manual_symbols=symbols,
            symbol_history=history[:100],
            theme=str(payload.get("theme", "openwallstreet-dark")),
            dense=bool(payload.get("dense", False)),
            unicode_symbols=bool(payload.get("unicode_symbols", True)),
        )

    def _read(self, path: Path) -> UISettings:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise UISettingsError("UI settings must contain a JSON object.")
        return self._decode(payload)

    def load(self) -> UISettings:
        if not self.path.exists():
            return UISettings()
        try:
            return self._read(self.path)
        except (OSError, json.JSONDecodeError, UISettingsError, TypeError, ValueError) as exc:
            if self.backup_path.exists():
                try:
                    recovered = self._read(self.backup_path)
                    self.load_warning = f"Recovered UI settings from backup after: {type(exc).__name__}."
                    return recovered
                except (OSError, json.JSONDecodeError, UISettingsError, TypeError, ValueError):
                    pass
            self.load_warning = f"UI settings could not be loaded: {type(exc).__name__}. Defaults are active."
            return UISettings()

    def save(self, settings: UISettings | None = None) -> None:
        settings = settings or self.settings
        settings.manual_symbols = self.normalize_symbols(settings.manual_symbols)
        settings.schema_version = SCHEMA_VERSION
        payload = asdict(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            self.backup_path.write_bytes(self.path.read_bytes())
            os.chmod(self.backup_path, 0o600)
        fd, raw_temp = tempfile.mkstemp(prefix=".ui.", suffix=".json", dir=self.path.parent)
        temp_path = Path(raw_temp)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            os.chmod(self.path, 0o600)
            try:
                directory_fd = os.open(self.path.parent, os.O_DIRECTORY)
            except (AttributeError, OSError):
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            self.settings = settings
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def update_history(self, symbols: list[str]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        by_symbol = {entry.symbol: entry for entry in self.settings.symbol_history}
        for symbol in self.normalize_symbols(symbols):
            entry = by_symbol.get(symbol)
            if entry is None:
                by_symbol[symbol] = SymbolHistoryEntry(symbol=symbol, last_used=now, usage_count=1)
            else:
                entry.last_used = now
                entry.usage_count += 1
        ranked = sorted(by_symbol.values(), key=lambda entry: (entry.usage_count, entry.last_used), reverse=True)
        self.settings.symbol_history = ranked[:100]

    def suggestions(self, prefix: str = "", limit: int = 8) -> list[str]:
        prefix = prefix.strip().upper()
        return [
            entry.symbol
            for entry in self.settings.symbol_history
            if not prefix or entry.symbol.startswith(prefix)
        ][:limit]
