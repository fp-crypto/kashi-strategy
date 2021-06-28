import brownie
from brownie import Contract
import pytest


def test_multiple_users_shutdown(
    chain,
    accounts,
    token,
    vault,
    strategy,
    user,
    user_2,
    strategist,
    amount,
    amount_2,
    kashi_pairs,
    RELATIVE_APPROX,
):
    # Deposit to the vault
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    assert token.balanceOf(vault.address) == amount

    # Harvest 1: Send funds through the strategy
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # Sleep for a while to earn yield
    chain.sleep(360)
    chain.mine(27)

    token.approve(vault.address, amount, {"from": user_2})
    vault.deposit(amount_2, {"from": user_2})
    assert token.balanceOf(vault.address) >= amount_2

    # Sleep for a while to earn yield
    chain.sleep(3600)
    chain.mine(270)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount + amount_2
    assert vault.pricePerShare() >= before_pps

    strategy.setEmergencyExit()
    strategy.harvest()
    chain.sleep(3600 * 10)  # 6 hrs needed for profits to unlock
    chain.mine(1)

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user_2})
    assert token.balanceOf(user_2) > amount_2
    assert pytest.approx(token.balanceOf(user_2), rel=RELATIVE_APPROX) == amount_2 * (
        before_pps / 10 ** vault.decimals()
    )
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()

    # Sleep for a while to earn yield
    chain.sleep(3600)
    chain.mine(270)

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount * (
        before_pps / 10 ** vault.decimals()
    )
    assert before_pps <= vault.pricePerShare()
