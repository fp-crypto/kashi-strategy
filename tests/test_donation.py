import brownie
from brownie import Contract
import pytest


def test_want_donation(
    chain, accounts, token, reserve, vault, strategy, RELATIVE_APPROX
):
    # donate want tokens
    token.transfer(strategy, 1_000 * 10 ** token.decimals(), {"from": reserve})

    # harvest
    before_pps = vault.pricePerShare()
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == 0
    chain.sleep(3600 * 6)
    chain.mine(1)
    assert before_pps < vault.pricePerShare()


def test_sushi_donation(
    chain, accounts, sushi, sushi_whale, vault, strategy, RELATIVE_APPROX
):
    # donate want tokens
    sushi.transfer(strategy, 1_000 * 10 ** sushi.decimals(), {"from": sushi_whale})

    # harvest
    before_pps = vault.pricePerShare()
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == 0
    chain.sleep(3600 * 6)
    chain.mine(1)
    assert before_pps < vault.pricePerShare()
