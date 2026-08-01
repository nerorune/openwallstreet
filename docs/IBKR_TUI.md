# MMR IBKR Textual terminal

This checkout is pinned to upstream `781453bd1be545f21d12df2bcc1ee3a800d06ce6`.
The Textual client (`trader/tui.py`) uses the MMR SDK, which uses MMR's local
ZeroMQ RPC/PubSub services. It does not open a separate IBKR connection.

## Safety and storage

The installed user configuration is `~/.config/mmr/trader.yaml` (mode 0600,
directory 0700). It defaults to `trading_mode: paper`, requires proposal
approval, caps opening orders at $1,000, options at five contracts / $500
estimated debit, and keeps MMR ports local. DuckDB events, proposals and order
history remain in `~/.local/share/mmr/data`; no credentials are stored there.

`docker-compose.yml` binds all IBKR, VNC, MMR RPC, dashboard, and pycron ports
to localhost. Keep `MMR_DILL_STRICT=1` available for strict structured-only
local messaging when compatible with the desired data stream.

## Commands

```bash
cd ~/ibkr-tui
./scripts/ibkr-tui setup       # configure paper API host/port/account; no password needed
./scripts/ibkr-tui login       # credential-consent guard; MFA remains interactive
./scripts/ibkr-tui start       # host services + Docker IB Gateway hybrid mode
./scripts/ibkr-tui reconnect   # controlled paper stack restart
./scripts/ibkr-tui tui         # live MMR-backed terminal
./scripts/ibkr-tui demo        # deterministic, no-IBKR terminal
./scripts/ibkr-tui doctor      # MMR verification
./scripts/ibkr-tui logs
./scripts/ibkr-tui stop        # safe stop; does not remove volumes
```

`mmr tui` refreshes account, positions, orders, proposals, and the watchlist
through MMR. `P` opens a limit-order preview, `A` approves the selected
proposal only after a Y confirmation, `X` rejects it, `R` refreshes and `D`
shows diagnostics. A preview cannot transmit. Approval calls MMR, whose
proposal transition, risk checks, account pinning and duplicate/retry controls
remain authoritative. The compact layout activates below 80 columns for SSH,
tmux, and mobile terminals.

## IBKR paper login

For this headless host, the intended deployment is Docker IB Gateway plus host
MMR services. Use only the paper API port selected during setup (normally the
project's localhost `7497` mapping); do not enable `--live`. Before any
credential is supplied, obtain explicit operator consent identifying whether it
will be typed into the IB Gateway VNC UI or placed in a protected secret. MFA
cannot be bypassed. On successful login, verify `mmr status --json`, retrieve
account/positions/orders, and use `mmr snapshot QQQ` / `mmr listen QQQ` to
confirm real ticks or an explicitly delayed state.

## Updating upstream

```bash
git fetch origin
git rebase origin/master
uv sync --all-extras
uv run pytest -q
```

Resolve conflicts without weakening order, RPC, account or deserialization
guards. Live trading and unattended execution are deliberately out of scope.
