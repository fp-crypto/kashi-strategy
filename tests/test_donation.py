import brownie
from brownie import Contract
import pytest


def test_want_donation(
    chain, accounts, user, gov, amount, token, reserve, vault, strategy, RELATIVE_APPROX
):
    # Deposit to the vault
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    assert token.balanceOf(vault.address) == amount

    strategy.harvest()

    # earn some yield
    chain.sleep(3600)
    chain.mine(270)

    # donate want tokens
    donation_amount = 1000 * 10 ** token.decimals()
    token.transfer(strategy, donation_amount, {"from": reserve})
    assert token.balanceOf(strategy) == donation_amount

    # Don't do healthCheck so we can have >300bps profit
    strategy.setDoHealthCheck(False, {"from": gov})

    # harvest
    before_pps = vault.pricePerShare()
    chain.sleep(1)
    tx = strategy.harvest()
    profit = tx.events["Harvested"]["profit"]
    assert profit >= donation_amount
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount
    chain.sleep(3600 * 6)
    chain.mine(1)
    assert before_pps < vault.pricePerShare()


def test_sushi_donation(
    chain,
    accounts,
    user,
    token,
    amount,
    sushi,
    sushi_whale,
    vault,
    strategy,
    RELATIVE_APPROX,
):
    # Deposit to the vault
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    assert token.balanceOf(vault.address) == amount

    # Harvest 1: Send funds through the strategy
    chain.sleep(1)

    # donate sushi tokens
    donation_amount = 1_000 * 10 ** sushi.decimals()
    sushi.transfer(strategy, donation_amount, {"from": sushi_whale})
    assert sushdi.balanceOf(strategy) == donation_amount

    # harvest
    before_pps = vault.pricePerShare()
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount
    chain.sleep(3600 * 6)
    chain.mine(1)
    assert before_pps < vault.pricePerShare()
