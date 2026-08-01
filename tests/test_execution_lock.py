"""The live-data execution lock must refuse before any IB client call."""

from types import SimpleNamespace

import pytest
from ib_async import Contract, MarketOrder

from trader.trading.approved_order import mint_approved_order
from trader.trading.executioner import TradeExecutioner


@pytest.mark.asyncio
async def test_final_placement_chokepoint_refuses_when_execution_is_locked() -> None:
    executor = TradeExecutioner()
    executor.trader = SimpleNamespace(execution_enabled=False)
    token = mint_approved_order(
        Contract(symbol="QQQ", secType="STK", exchange="SMART", currency="USD"),
        MarketOrder("BUY", 1),
        is_exit=False,
        checks={"risk": "pass"},
    )

    errors: list[Exception] = []
    observable = await executor.subscribe_place_order_direct(token)
    observable.subscribe(on_error=errors.append)

    assert len(errors) == 1
    assert isinstance(errors[0], PermissionError)
    assert "no order was sent" in str(errors[0])
