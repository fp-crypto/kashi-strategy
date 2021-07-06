import pytest
import brownie
from brownie import Wei, accounts, Contract, config, Hack


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
    reserve,
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
    vault.removeStrategyFromQueue(strategy, {"from": gov})
    vault.addStrategy(new_strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})

    hack = user.deploy(Hack, vault, token)
    user_start_balance = token.balanceOf(user)
    before_pps = vault.pricePerShare()
    token.transfer(hack, user_start_balance, {"from": user})
    print(f"Balance of Hack: {token.balanceOf(hack)/1e6:_}")
    hack.deposit()
    token.transfer(new_strategy, 1_000 * 1e6, {"from": reserve})

    # Get profits and withdraw
    print(before_pps)
    before_pps = vault.pricePerShare()
    vault.setStrategyEnforceChangeLimit(new_strategy, False, {"from": gov})
    tx = new_strategy.harvest({"from": gov})
    chain.sleep(3600 * 6)
    chain.mine(1)

    hack.loop(8)
    print(f"token balance end of loop: {token.balanceOf(hack)/1e6:_}")
    hack.deposit()

    hack.loop(8)
    print(f"token balance end of loop: {token.balanceOf(hack)/1e6:_}")
    hack.deposit()

    hack.loop(8)
    print(f"token balance end of loop: {token.balanceOf(hack)/1e6:_}")
    hack.deposit()

    hack.loop(8)
    print(f"token balance end of loop: {token.balanceOf(hack)/1e6:_}")
    hack.deposit()
