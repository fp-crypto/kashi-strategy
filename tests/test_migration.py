import pytest
import brownie
from brownie import Contract


def test_migration(
    chain,
    token,
    vault,
    strategy,
    amount,
    Strategy,
    strategist,
    gov,
    user,
    RELATIVE_APPROX,
    bento_box,
    kashi_pair,
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # migrate to a new strategy
    new_strategy = strategist.deploy(Strategy, vault, bento_box, kashi_pair)
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})
    assert (
        pytest.approx(new_strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX)
        == amount
    )


def test_new_kashi_pair(token, vault, strategy, amount, gov, user, RELATIVE_APPROX):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    new_token_vault = Contract("0x591f6fd601DAD61B9565A7896977BaF69aA403c2")

    strategy.setKashiPair(new_token_vault.address, {"from": gov})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount


def test_invalid_new_kashi_pair(
    token, vault, strategy, amount, gov, user, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    invalid_kashi_pair = Contract("0x11111112542D85B3EF69AE05771c2dCCff4fAa26")
    with brownie.reverts():
        strategy.setKashiPair(invalid_kashi_pair, {"from": gov})

    invalid_kashi_pair = Contract("0xeA3d9D00de6C14bf8507f46C46c29292bBFA8D25")
    with brownie.reverts():
        strategy.setKashiPair(invalid_kashi_pair, {"from": gov})
