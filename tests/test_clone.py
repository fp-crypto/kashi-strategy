import pytest
import brownie
from brownie import Wei, accounts, Contract, config


def test_clone(
    chain,
    gov,
    token,
    strategist,
    rewards,
    keeper,
    strategy,
    Strategy,
    vault,
    bento_box,
    kashi_pairs,
    pids,
    user,
    amount,
):
    # Shouldn't be able to call initialize again
    with brownie.reverts():
        strategy.initialize(
            vault,
            strategist,
            rewards,
            keeper,
            bento_box,
            kashi_pairs,
            pids,
            "",
            {"from": gov},
        )

    # Clone the strategy
    tx = strategy.cloneKashiLender(
        vault,
        strategist,
        rewards,
        keeper,
        bento_box,
        kashi_pairs,
        pids,
        "",
        {"from": gov},
    )
    new_strategy = Strategy.at(tx.return_value)

    # Shouldn't be able to call initialize again
    with brownie.reverts():
        new_strategy.initialize(
            vault,
            strategist,
            rewards,
            keeper,
            bento_box,
            kashi_pairs,
            pids,
            "",
            {"from": gov},
        )

    vault.revokeStrategy(strategy, {"from": gov})
    vault.addStrategy(new_strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})

    user_start_balance = token.balanceOf(user)
    before_pps = vault.pricePerShare()
    token.approve(vault.address, amount, {"from": user})
    vault.deposit({"from": user})

    new_strategy.harvest({"from": gov})

    chain.sleep(3600)
    chain.mine(270)

    # Get profits and withdraw
    new_strategy.harvest({"from": gov})
    chain.sleep(3600 * 10)
    chain.mine(1)

    vault.withdraw({"from": user})
    user_end_balance = token.balanceOf(user)

    assert vault.pricePerShare() > before_pps
    assert user_end_balance > user_start_balance
