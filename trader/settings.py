"""Safe, local settings support for the OpenWallStreet Textual client.

This module deliberately has no IBKR imports.  Runtime values are obtained via
the public MMR SDK by the TUI, while files here only hold operator-owned
preferences and the configuration MMR reads when it is restarted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from enum import Enum
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Callable, Mapping

import yaml

from trader.trading.risk_gate import RiskLimits


class SettingsError(ValueError):
    """An operator-facing settings error that is safe to display."""


class Impact(str, Enum):
    NOW = "applies now"
    RESTART_MMR = "restart MMR"
    RESTART_GATEWAY = "restart Gateway + MFA"


RISK_LIMIT_KEYS = frozenset(field.name for field in fields(RiskLimits))
SECRET_MARKERS = ("password", "secret", "token", "key", "userid", "username")


def protected_write(path: Path, text: str) -> None:
    """Atomically write a user configuration with owner-only permissions."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def permission_health(path: Path) -> str:
    """Return a non-secret file-permission health label."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return "missing"
    return "healthy (0600)" if mode == 0o600 else f"unsafe ({mode:04o}; expected 0600)"


class YAMLStore:
    """Mapping-only YAML store that recovers safely from malformed input."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.error = ""

    def load(self) -> dict[str, Any]:
        self.error = ""
        if not self.path.exists():
            return {}
        try:
            parsed = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            self.error = f"Could not parse {self.path.name}: {type(exc).__name__}"
            return {}
        if not isinstance(parsed, dict):
            self.error = f"Could not parse {self.path.name}: top-level mapping required"
            return {}
        return parsed

    def save(self, value: Mapping[str, Any]) -> None:
        protected_write(self.path, yaml.safe_dump(dict(value), sort_keys=False))


class MMRConfigStore(YAMLStore):
    def __init__(self, path: Path | None = None) -> None:
        super().__init__(path or Path(os.environ.get("TRADER_CONFIG", "~/.config/mmr/trader.yaml")))

    def risk_limits(self) -> dict[str, Any]:
        raw = self.load().get("risk_limits", {})
        return dict(raw) if isinstance(raw, dict) else {}

    def save_risk_limits(self, limits: Mapping[str, Any]) -> None:
        config = self.load()
        config["risk_limits"] = dict(limits)
        self.save(config)


class UIPreferencesStore(YAMLStore):
    """OpenWallStreet-owned UI preferences, isolated from MMR's config."""

    DEFAULTS = {"theme": "dark", "dense": True, "watchlist": []}

    def __init__(self, path: Path | None = None) -> None:
        super().__init__(path or Path("~/.config/openwallstreet/ui.yaml"))

    def preferences(self) -> dict[str, Any]:
        result = dict(self.DEFAULTS)
        result.update(self.load())
        # There is intentionally no light theme: the terminal has a single,
        # high-contrast operational palette.
        result["theme"] = "dark"
        result["dense"] = bool(result.get("dense", True))
        result["watchlist"] = list(result.get("watchlist") or [])
        return result

    def validate(self, value: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(self.DEFAULTS)
        result.update(value)
        if result.get("theme") != "dark":
            raise SettingsError("Only the dark operational theme is supported.")
        if not isinstance(result.get("dense"), bool):
            raise SettingsError("Dense layout must be enabled or disabled.")
        watchlist = result.get("watchlist")
        if not isinstance(watchlist, list) or not all(isinstance(item, str) and item.isalpha() for item in watchlist):
            raise SettingsError("Watchlist must contain ticker symbols only.")
        return result


@dataclass(frozen=True)
class CredentialHealth:
    source: str
    present: bool
    permissions: str


class CredentialStore:
    """Credential replacement without ever loading an existing secret.

    The store intentionally does not inspect the contents of ``.env``.  Its
    presence is a file-level status only; replacement is a complete atomic
    credential-file write, so callers must supply both values.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or Path(".env")).expanduser()

    def health(self) -> CredentialHealth:
        return CredentialHealth(str(self.path), self.path.is_file(), permission_health(self.path))

    def replace_gateway_credentials(self, username: str, password: str, *, confirmed: bool) -> None:
        if not confirmed:
            raise SettingsError("Credential replacement requires explicit confirmation.")
        if not username.strip() or not password:
            raise SettingsError("Both username and password are required.")
        # Do not retain either value on this object or return it to a caller.
        protected_write(self.path, f"TWS_USERID={username.strip()}\nTWS_PASSWORD={password}\n")


def redact_value(key: str, value: Any) -> str:
    key_lower = key.lower()
    if any(marker in key_lower for marker in SECRET_MARKERS):
        return "[redacted]"
    rendered = repr(value)
    return "[redacted]" if len(rendered) > 160 else rendered


def redacted_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Small, safe-to-render diff for the review screen."""
    changes = []
    for key in sorted(set(before) | set(after)):
        left, right = before.get(key), after.get(key)
        if left != right:
            changes.append(f"{key}: {redact_value(key, left)} → {redact_value(key, right)}")
    return changes


def validate_risk_limits(changes: Mapping[str, Any]) -> dict[str, Any]:
    valid: dict[str, Any] = {}
    defaults = asdict(RiskLimits())
    unknown = set(changes) - RISK_LIMIT_KEYS
    if unknown:
        raise SettingsError(f"Unknown risk limit: {sorted(unknown)[0]}")
    for key, value in changes.items():
        try:
            converted = type(defaults[key])(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError(f"{key} must be a {type(defaults[key]).__name__}.") from exc
        if converted < 0:
            raise SettingsError(f"{key} cannot be negative.")
        if key in {"max_position_size_pct", "min_margin_cushion"} and converted > 1:
            raise SettingsError(f"{key} must be between 0 and 1.")
        if key == "max_leverage" and converted < 1:
            raise SettingsError("max_leverage must be at least 1.")
        valid[key] = converted
    return valid


@dataclass
class SettingsDraft:
    mmr: MMRConfigStore
    ui: UIPreferencesStore
    config: dict[str, Any]
    preferences: dict[str, Any]
    risk_changes: dict[str, Any]

    @classmethod
    def open(cls, mmr: MMRConfigStore | None = None, ui: UIPreferencesStore | None = None) -> "SettingsDraft":
        mmr, ui = mmr or MMRConfigStore(), ui or UIPreferencesStore()
        return cls(mmr, ui, mmr.load(), ui.preferences(), {})

    @property
    def dirty(self) -> bool:
        return bool(self.risk_changes) or self.preferences != self.ui.preferences()

    def set_risk(self, key: str, value: Any) -> None:
        self.risk_changes.update(validate_risk_limits({key: value}))

    def toggle_dense(self) -> None:
        self.preferences["dense"] = not bool(self.preferences.get("dense", True))

    def impacts(self) -> set[Impact]:
        impacts: set[Impact] = set()
        if self.risk_changes:
            impacts.add(Impact.NOW)
        if self.preferences != self.ui.preferences():
            impacts.add(Impact.NOW)
        return impacts

    def diff(self) -> list[str]:
        lines = redacted_diff(self.ui.preferences(), self.preferences)
        old_risk = self.config.get("risk_limits", {}) if isinstance(self.config.get("risk_limits"), dict) else {}
        lines.extend(f"risk_limits.{line}" for line in redacted_diff(old_risk, {**old_risk, **self.risk_changes}))
        return lines

    def discard(self) -> None:
        self.config = self.mmr.load()
        self.preferences = self.ui.preferences()
        self.risk_changes.clear()

    def apply(self, set_live_risk: Callable[..., Mapping[str, Any]] | None = None) -> None:
        if self.risk_changes:
            if set_live_risk is None:
                raise SettingsError("MMR is unavailable; risk limits were not changed.")
            updated = dict(set_live_risk(**self.risk_changes))
            self.mmr.save_risk_limits(updated)
            self.config = self.mmr.load()
            self.risk_changes.clear()
        validated = self.ui.validate(self.preferences)
        self.ui.save(validated)
        self.preferences = validated


@dataclass(frozen=True)
class LiveExecutionRequest:
    account: str
    mode: str
    typed_confirmation: str
    risk_acknowledged: bool
    gateway_read_only: bool


def validate_live_execution_request(request: LiveExecutionRequest) -> None:
    """Gate live mode before any lifecycle action can be requested."""
    if request.mode.upper() != "LIVE":
        raise SettingsError("Live execution requires an explicit LIVE mode review.")
    if not request.account:
        raise SettingsError("Live execution requires a selected account.")
    if request.typed_confirmation != "ENABLE LIVE":
        raise SettingsError("Type ENABLE LIVE exactly to continue.")
    if not request.risk_acknowledged:
        raise SettingsError("Risk acknowledgement is required.")
    if request.gateway_read_only:
        raise SettingsError("Gateway remains read-only; restart it with MFA before live mode.")


class GatewayLifecycle:
    """Command selection for the existing local wrapper; never calls IBKR."""

    ACTIONS = {
        "start_login": ("./docker.sh", "--ib-only"),
        "stop": ("./docker.sh", "--stop-ib"),
        "reconnect": ("./docker.sh", "--restart-ib"),
        "logs": ("./docker.sh", "--ib-logs"),
    }

    @classmethod
    def command(cls, action: str) -> tuple[str, ...]:
        try:
            return cls.ACTIONS[action]
        except KeyError as exc:
            raise SettingsError(f"Unsupported Gateway action: {action}") from exc
