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
    kashi_pairs,
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # migrate to a new strategy
    new_strategy = strategist.deploy(Strategy, vault, bento_box, kashi_pairs)
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})
    assert (
        pytest.approx(new_strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX)
        == amount
    )


def test_new_kashi_pair(
    token, vault, strategy, amount, gov, user, kashi_pairs, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    new_kashi_pair = Contract("0x40a12179260997c55619DE3290c5b9918588E791")

    strategy.addKashiPair(new_kashi_pair, {"from": gov})
    assert strategy.kashiPairs(len(kashi_pairs)) == new_kashi_pair.address

    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount


def test_add_existing_kashi_pair(
    token, vault, strategy, amount, gov, user, kashi_pair_0, RELATIVE_APPROX
):
    with brownie.reverts():
        strategy.addKashiPair(kashi_pair_0, {"from": gov})


def test_remove_kashi_pair(
    token,
    vault,
    strategy,
    amount,
    gov,
    user,
    kashi_pairs,
    kashi_pair_0,
    RELATIVE_APPROX,
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.removeKashiPair(kashi_pair_0, {"from": gov})
    assert strategy.kashiPairs(0) != kashi_pair_0.address

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
        strategy.addKashiPair(invalid_kashi_pair, {"from": gov})

    invalid_kashi_pair = Contract("0x809F2B68f59272740508333898D4e9432A839C75")
    with brownie.reverts():
        strategy.addKashiPair(invalid_kashi_pair, {"from": gov})
