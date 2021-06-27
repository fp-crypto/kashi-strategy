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
    pids,
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.adjustKashiPairRatios([4000, 1500, 2500, 2000], {"from": strategist})

    before_assets = [
        strategy.kashiPairEstimatedAssets(i) for i in range(len(kashi_pairs))
    ]

    # migrate to a new strategy
    name = "NewStrat"
    new_strategy = strategist.deploy(
        Strategy, vault, bento_box, kashi_pairs, pids, name
    )
    vault.migrateStrategy(strategy, new_strategy, {"from": gov})
    assert (
        pytest.approx(new_strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX)
        == amount
    )
    assert new_strategy.name() == name

    for (i, before_asset) in enumerate(before_assets):
        assert new_strategy.kashiPairEstimatedAssets(i) == before_asset


def test_new_kashi_pair(
    chain, token, vault, strategy, amount, gov, user, kashi_pairs, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})

    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    new_kashi_pair = Contract("0x40a12179260997c55619DE3290c5b9918588E791")
    strategy.addKashiPair(new_kashi_pair, 0, {"from": gov})
    assert (
        strategy.kashiPairs(len(kashi_pairs)).dict()["kashiPair"]
        == new_kashi_pair.address
    )
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount


def test_add_existing_kashi_pair(
    chain, token, vault, strategy, amount, gov, user, kashi_pair_0, RELATIVE_APPROX
):
    with brownie.reverts():
        strategy.addKashiPair(kashi_pair_0, 0, {"from": gov})


def test_remove_kashi_pair(
    chain,
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

    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.removeKashiPair(kashi_pair_0, 0, {"from": gov})
    assert strategy.kashiPairs(0)[0] != kashi_pair_0.address
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount


def test_invalid_new_kashi_pair(
    chain, token, vault, strategy, amount, gov, user, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})

    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    invalid_kashi_pair = Contract("0x11111112542D85B3EF69AE05771c2dCCff4fAa26")
    with brownie.reverts():
        strategy.addKashiPair(invalid_kashi_pair, 0, {"from": gov})

    invalid_kashi_pair = Contract("0x809F2B68f59272740508333898D4e9432A839C75")
    with brownie.reverts():
        strategy.addKashiPair(invalid_kashi_pair, 0, {"from": gov})
