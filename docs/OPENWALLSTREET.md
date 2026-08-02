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
`781453bd1be545f21d12df2bcc1ee3a800d06ce6`.

MMR remains the backend owner for IBKR connectivity, service messaging,
contracts, portfolio state, proposals, risk, execution boundaries, strategy
runtime, and persistence. OpenWallStreet adds the product-facing terminal,
deployment ergonomics, documentation, operational diagnostics, and hardening
required for a local workstation.

The boundary is intentional:

| Responsibility | Owner |
| --- | --- |
| IBKR connection and reconnection | MMR service layer |
| Contract resolution, portfolio, proposals, risk, and final execution gate | MMR |
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
4. Track upstream MMR changes through a named `upstream` remote and retain
   small, reviewable local commits for mergeability.

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
