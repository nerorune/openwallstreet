# OpenWallStreet contributor guide

OpenWallStreet is an under-development MMR-derived workstation. MMR is the
only trading backend. `trader/tui.py` is a Textual client of its SDK/RPC
surfaces; it must never create an independent `ib_async` session or traverse
internal service objects.

Keep the fork's purpose clear: OpenWallStreet owns terminal UX, lifecycle
tooling, documentation, and safety hardening; MMR owns IBKR connectivity,
contracts, proposals, risk, execution, services, and storage. Preserve the
upstream license and notices, maintain the `upstream` remote, and keep local
changes modular and mergeable.

Paper mode is the default and live trading must remain disabled unless an
operator deliberately changes the secured user configuration. New exposure
must preserve MMR's proposal → review → approve boundary and its final
executioner risk/account checks. Do not add a TUI-only bypass.

IBKR connectivity is owned by `trader/listeners/ibreactive.py`; proposals and
execution are owned by `trader/sdk.py`, `trader/messaging/trader_service_api.py`,
and `trader/trading/executioner.py`. Keep RPC methods decorated with
`@rpcmethod`, local-only, and single-segment. Preserve restricted messaging
deserialization.

Run `uv run pytest -q`, `uv run ty check`, and `uv run mmr tui --demo` for
changes. Never commit credentials, MFA values, account IDs, `.env`,
`~/.config/mmr/secrets.env`, or DuckDB data. The repository is public but
direct write access remains owner-only until a contribution process is
documented.
