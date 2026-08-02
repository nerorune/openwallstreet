# Upstream relationship

OpenWallStreet began as a fork of [9600dev/mmr](https://github.com/9600dev/mmr)
at commit `781453bd1be545f21d12df2bcc1ee3a800d06ce6`.

It is now a single, maintained OpenWallStreet source tree. Users clone and run
this repository only; they do not need an MMR submodule, sibling checkout, or
separate MMR runtime. The included MMR-derived Python services and their RPC
interfaces are part of OpenWallStreet's build and release surface.

## Policy

The Git remote named `upstream` points to the MMR repository. We watch it for
useful fixes and may merge or cherry-pick them after review. Each upstream
change must be evaluated against OpenWallStreet's local UX, lifecycle, safety,
execution-lock, secret-handling, and test requirements.

OpenWallStreet intentionally diverges from the base commit. We preserve
upstream attribution, license terms, and notices, but do not promise
byte-for-byte compatibility or automatic synchronization. The authoritative
code for a running OpenWallStreet installation is the checkout that its
`openwallstreet` launcher resolves to.

## Practical guidance

- Keep the `upstream` remote configured; do not turn the upstream repository
  into a runtime dependency.
- Fetch and inspect upstream changes before integrating them.
- Prefer small, reviewable merges or cherry-picks with focused regression tests.
- Record material upstream integrations in commit messages or release notes.
- Do not replace local safety controls merely to reduce merge conflict.
