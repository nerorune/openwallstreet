# OpenWallStreet project boundary

## Status

OpenWallStreet is public and under active development. It is currently a
local-first workstation for Interactive Brokers account monitoring, market
data, proposal review, and carefully controlled operator workflows. It is not
investment advice, a hosted trading service, or an unattended execution
system.

## Relationship to MMR

This repository began as a fork of
[9600dev/mmr](https://github.com/9600dev/mmr) at upstream commit
`781453bd1be545f21d12df2bcc1ee3a800d06ce6`. From that commit forward,
OpenWallStreet is intentionally its own product and source tree. It is not a
wrapper around, submodule for, or runtime dependency on a second MMR checkout.

OpenWallStreet includes the MMR-derived IBKR connectivity, service messaging,
contracts, portfolio state, proposals, risk, execution boundaries, strategy
runtime, and persistence layers. It adds the product-facing terminal,
deployment ergonomics, documentation, operational diagnostics, and hardening
required for a local workstation.

The architectural boundary is intentional, but it is an ownership boundary
inside this repository—not a separate runtime:

| Responsibility | Owner |
| --- | --- |
| IBKR connection and reconnection | Included MMR-derived service layer |
| Contract resolution, portfolio, proposals, risk, and final execution gate | Included MMR-derived service layer |
| Terminal UX, presentation, keyboard workflow, and local lifecycle commands | OpenWallStreet |
| Credentials and MFA | Operator-controlled local environment only |

The TUI must consume MMR's SDK/RPC/PubSub interfaces. It must never start an
independent IBKR API session or bypass MMR's proposal, risk, account-pinning,
or final placement controls.

## Near-term direction

1. Make the Textual terminal a dependable read-only account and market-data
   workstation, including honest delayed/stale/unavailable labels.
2. Complete proposal, journal, option-inspection, diagnostics, and responsive
   SSH/mobile workflows while keeping paper execution the default.
3. Keep execution default-deny and separately test every safety boundary before
   expanding any operator-approved paper workflow.
4. Track upstream MMR changes through a named `upstream` remote and bring in
   selected improvements through reviewed merges or cherry-picks. Retain small,
   reviewable local commits for mergeability; this fork does not promise to
   remain byte-for-byte compatible with upstream.

## Governance and contributions

The repository is public for transparency and development visibility. At this
stage, `nerorune` is the sole administrator and direct writer. Issues and
discussions are disabled; no external maintainer or automated agent may merge
or deploy changes. Any future contribution process will be documented before
it is enabled.

## Licensing and naming

MMR-derived material remains under the repository's Apache-2.0-with-Commons-
Clause license. A fork does not remove the Commons Clause's restriction on
selling software or a service whose value derives substantially from the
software. Preserve `LICENSE.md`, upstream notices, and attribution when
redistributing derivative material.

OpenWallStreet is a project name for this fork; it is not an assertion of
affiliation with MMR or Interactive Brokers. Confirm trademark, regulatory,
and commercial licensing questions with appropriate professional advice before
any commercial release.

## Settings control center

`mmr tui` opens the OpenWallStreet settings center with `S`, or through `:` then `settings`. It is a Textual-only, dark operational interface; OpenTUI and a TypeScript/Zig runtime are deliberately not used.

Live state and supported risk-limit changes use the included MMR-derived
SDK/RPC service layer. UI preferences live in `~/.config/openwallstreet/ui.yaml`
(0600); the compatibility runtime configuration remains
`~/.config/mmr/trader.yaml` (0600). Settings are draft-first, show a redacted
diff and impact label, and require Apply or Discard. Connection, account, mode,
data-source, risk-limit, and next-start trading-mode changes can be edited;
Gateway changes remain queued until their restart action.

Gateway credentials are replacement-only in the existing `.env`: the UI never reads, pre-fills, logs, or displays existing secrets. Replacement needs both masked fields plus confirmation and is an atomic 0600 write. Gateway controls remain localhost-only, point operators to `vnc://localhost:5901`, and never bypass MFA.

Paper execution changes require an explicit controlled MMR restart. Live execution remains locked by default and requires a separate typed confirmation, account/mode review, risk acknowledgement, a read-write Gateway restart, and MFA. No settings path places an order.
