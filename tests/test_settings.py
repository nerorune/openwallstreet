"""Focused coverage for the OpenWallStreet settings safety boundary."""

from pathlib import Path
import stat

import pytest

from trader.settings import (
    CredentialStore,
    GatewayLifecycle,
    LiveExecutionRequest,
    MMRConfigStore,
    SettingsDraft,
    SettingsError,
    UIPreferencesStore,
    redacted_diff,
    validate_live_execution_request,
)


def test_risk_draft_applies_via_callback_and_persists(tmp_path: Path) -> None:
    mmr = MMRConfigStore(tmp_path / "trader.yaml")
    ui = UIPreferencesStore(tmp_path / "ui.yaml")
    draft = SettingsDraft.open(mmr, ui)
    draft.set_risk("max_daily_loss", "250")
    seen = {}
    draft.apply(lambda **changes: seen.update(changes) or {"max_daily_loss": 250.0})
    assert seen == {"max_daily_loss": 250.0}
    assert mmr.risk_limits() == {"max_daily_loss": 250.0}
    assert stat.S_IMODE((tmp_path / "trader.yaml").stat().st_mode) == 0o600


def test_malformed_yaml_recovers_without_throwing(tmp_path: Path) -> None:
    path = tmp_path / "trader.yaml"
    path.write_text("risk_limits: [not-a-mapping")
    store = MMRConfigStore(path)
    assert store.load() == {}
    assert "Could not parse" in store.error


def test_credential_replacement_needs_both_values_and_confirmation(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / ".env")
    with pytest.raises(SettingsError):
        store.replace_gateway_credentials("user", "", confirmed=True)
    with pytest.raises(SettingsError):
        store.replace_gateway_credentials("user", "pw", confirmed=False)
    store.replace_gateway_credentials("user", "pw", confirmed=True)
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
    assert store.health().present is True


def test_diff_redacts_secrets() -> None:
    diff = redacted_diff({"password": "old"}, {"password": "new"})
    assert "old" not in diff[0] and "new" not in diff[0]
    assert "[redacted]" in diff[0]


@pytest.mark.parametrize("live_request", [
    LiveExecutionRequest("", "LIVE", "ENABLE LIVE", True, False),
    LiveExecutionRequest("DU123", "PAPER", "ENABLE LIVE", True, False),
    LiveExecutionRequest("DU123", "LIVE", "no", True, False),
    LiveExecutionRequest("DU123", "LIVE", "ENABLE LIVE", False, False),
    LiveExecutionRequest("DU123", "LIVE", "ENABLE LIVE", True, True),
])
def test_live_wizard_refuses_incomplete_requests(live_request: LiveExecutionRequest) -> None:
    with pytest.raises(SettingsError):
        validate_live_execution_request(live_request)


def test_gateway_actions_stay_in_local_wrapper() -> None:
    assert GatewayLifecycle.command("start_login") == ("./docker.sh", "--ib-only")
    assert GatewayLifecycle.command("reconnect") == ("./docker.sh", "--restart-ib")
