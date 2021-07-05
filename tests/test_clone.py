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

    user_start_balance = token.balanceOf(user)
    before_pps = vault.pricePerShare()
    token.approve(vault.address, 2**256-1, {"from": user})
    vault.deposit({"from": user})

    token.transfer(new_strategy, 1_000 * 10 ** token.decimals(), {"from": reserve})

    # Get profits and withdraw
    print(before_pps)
    before_pps = vault.pricePerShare()
    new_strategy.harvest({"from": gov})
    chain.sleep(3600 * 6)
    chain.mine(1)
    #assert vault.pricePerShare() > before_pps
    
    before_pps = vault.pricePerShare()
    print(vault.pricePerShare())
    vault.withdraw({"from": user})

    for i in range(200):
        print(f"pps: {vault.pricePerShare()/1e6:_}")
        print(f"bal: {token.balanceOf(user)/1e6:_}")
        vault.deposit({"from": user})
        print(f"pps: {vault.pricePerShare()/1e6:_}")
        vault.withdraw({"from": user})

    print(f"pps: {vault.pricePerShare()/1e6:_}")

    #assert vault.pricePerShare() > before_pps
    #assert user_end_balance > user_start_balance
