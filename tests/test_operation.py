import brownie
from brownie import Contract
import pytest


def test_operation(
    chain, accounts, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
):
    # Deposit to the vault
    user_balance_before = token.balanceOf(user)
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    assert token.balanceOf(vault.address) == amount

    # harvest
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # tend()
    strategy.tend()

    # withdrawal
    vault.withdraw({"from": user})
    assert (
        pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == user_balance_before
    )


def test_emergency_exit(
    chain, accounts, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
):
    # Deposit to the vault
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # set emergency and exit
    strategy.setEmergencyExit()
    chain.sleep(1)
    strategy.harvest()
    assert strategy.estimatedTotalAssets() < amount


def test_profitable_harvest(
    chain, accounts, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
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
    chain.sleep(3600)
    chain.mine(270)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount
    assert vault.pricePerShare() > before_pps


def test_adjust_ratios(
    chain,
    accounts,
    token,
    vault,
    strategy,
    user,
    strategist,
    amount,
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
    chain.sleep(3600)
    chain.mine(270)

    strategy.adjustKashiPairRatios([2500, 2500, 2500, 2500], {"from": strategist})

    for n in range(1, len(kashi_pairs)):
        assert (
            pytest.approx(
                kashi_pair_in_want(kashi_pairs[0], strategy) / 10 ** token.decimals(),
                rel=RELATIVE_APPROX,
            )
            == kashi_pair_in_want(kashi_pairs[n], strategy) / 10 ** token.decimals()
        )

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 10)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount
    assert vault.pricePerShare() > before_pps

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount * (
        before_pps / 10 ** vault.decimals()
    )


def test_multiple_users(
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
    chain.sleep(360)
    chain.mine(27)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount + amount_2
    assert vault.pricePerShare() > before_pps

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user_2})
    assert token.balanceOf(user_2) > amount_2
    assert pytest.approx(token.balanceOf(user_2), rel=RELATIVE_APPROX) == amount_2 * (
        before_pps / 10 ** vault.decimals()
    )
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()

    # Sleep for a while to earn yield
    chain.sleep(360)
    chain.mine(27)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 10)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    assert vault.pricePerShare() > before_pps

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount * (
        before_pps / 10 ** vault.decimals()
    )
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()


def test_multiple_users_and_adjust_ratios(
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

    strategy.adjustKashiPairRatios([2500, 2500, 2500, 2500], {"from": strategist})

    for n in range(1, len(kashi_pairs)):
        assert (
            pytest.approx(
                kashi_pair_in_want(kashi_pairs[0], strategy) / 10 ** token.decimals(),
                rel=RELATIVE_APPROX,
            )
            == kashi_pair_in_want(kashi_pairs[n], strategy) / 10 ** token.decimals()
        )

    token.approve(vault.address, amount, {"from": user_2})
    vault.deposit(amount_2, {"from": user_2})
    assert token.balanceOf(vault.address) >= amount_2

    # Sleep for a while to earn yield
    chain.sleep(360)
    chain.mine(27)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount + amount_2
    assert vault.pricePerShare() > before_pps

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user_2})
    assert token.balanceOf(user_2) > amount_2
    assert pytest.approx(token.balanceOf(user_2), rel=RELATIVE_APPROX) == amount_2 * (
        before_pps / 10 ** vault.decimals()
    )
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()

    # Sleep for a while to earn yield
    chain.sleep(360)
    chain.mine(27)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 10)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    assert vault.pricePerShare() > before_pps

    strategy.adjustKashiPairRatios([4000, 2000, 2000, 2000], {"from": strategist})
    for n in range(1, len(kashi_pairs)):
        assert (
            pytest.approx(
                kashi_pair_in_want(kashi_pairs[0], strategy) / 10 ** token.decimals(),
                rel=RELATIVE_APPROX,
            )
            == kashi_pair_in_want(kashi_pairs[n], strategy) * 2 / 10 ** token.decimals()
        )

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount * (
        before_pps / 10 ** vault.decimals()
    )
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()


def test_change_debt(
    chain, gov, token, vault, strategy, user, strategist, amount, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    chain.sleep(1)
    strategy.harvest()
    half = int(amount / 2)

    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half

    vault.updateStrategyDebtRatio(strategy.address, 10_000, {"from": gov})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half


def test_sweep(gov, vault, strategy, token, user, amount, weth, weth_amout):
    # Strategy want token doesn't work
    token.transfer(strategy, amount, {"from": user})
    assert token.address == strategy.want()
    assert token.balanceOf(strategy) > 0
    with brownie.reverts("!want"):
        strategy.sweep(token, {"from": gov})

    # Vault share token doesn't work
    with brownie.reverts("!shares"):
        strategy.sweep(vault.address, {"from": gov})

    before_balance = weth.balanceOf(gov)
    weth.transfer(strategy, weth_amout, {"from": user})
    assert weth.address != strategy.want()
    assert weth.balanceOf(user) == 0
    strategy.sweep(weth, {"from": gov})
    assert weth.balanceOf(gov) == weth_amout + before_balance


def kashi_pair_in_want(kashi_pair, account):
    kashi_fraction = kashi_pair.balanceOf(account)
    bento_box = Contract(kashi_pair.bentoBox())
    token = Contract(kashi_pair.asset())
    total_asset = kashi_pair.totalAsset().dict()
    total_borrow = kashi_pair.totalBorrow().dict()
    all_share = total_asset["elastic"] + bento_box.toShare(
        token, total_borrow["elastic"], True
    )
    bento_shares = (kashi_fraction * all_share) / total_asset["base"]
    return bento_box.toAmount(token, bento_shares, True)
