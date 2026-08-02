# OpenWallStreet contributor guide

OpenWallStreet is an under-development workstation built from the MMR codebase
at a documented upstream commit. It is one repository and one runtime, not an
OpenWallStreet shell around a separately checked-out MMR installation.
`trader/tui.py` is a Textual client of the included MMR-derived service/RPC
surfaces; it must never create an independent `ib_async` session or traverse
internal service objects.

Keep the fork's purpose clear: OpenWallStreet owns the complete product,
including terminal UX, lifecycle tooling, documentation, safety hardening, and
the included MMR-derived connectivity, service, risk, execution, and storage
layers. The upstream MMR project is acknowledged and tracked through the
`upstream` remote, but this fork intentionally diverges after its base commit.
Bring upstream improvements in through deliberate, reviewed merges or
cherry-picks; do not assume this tree stays byte-for-byte compatible. Preserve
upstream license and notices and keep local changes modular and mergeable.

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
changes.

Settings ownership: `trader/settings.py` owns protected config writes, diff redaction, execution gates, and no-secret credential replacement; `trader/settings_tui.py` owns Textual presentation only. Keep settings on MMR SDK/RPC surfaces and local lifecycle wrappers. Never read, pre-fill, log, or display `.env` credentials; credential writes must be atomic 0600. Gateway restarts require MFA and preserve localhost-only networking. OpenTUI is deliberately excluded; do not add a TypeScript/Zig runtime.
Never commit credentials, MFA values, account IDs, `.env`,
`~/.config/mmr/secrets.env`, or DuckDB data. The repository is public but
direct write access remains owner-only until a contribution process is
documented.
