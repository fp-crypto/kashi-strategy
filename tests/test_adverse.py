import brownie
from brownie import Contract
import pytest


def test_borrow_all_withdraw(
    chain,
    accounts,
    token,
    vault,
    strategy,
    user,
    strategist,
    amount,
    kashi_pair_0,
    borrower,
    collateral_amount,
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

    strategy.adjustKashiPairRatios([10000, 0, 0, 0], {"from": strategist})

    # Sleep for a while to earn yield
    chain.sleep(360)
    chain.mine(27)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount
    assert vault.pricePerShare() >= before_pps

    borrow_all(kashi_pair_0, borrower)

    # The user is only able to make an incomplete withdraw
    vault.withdraw({"from": user})
    assert vault.balanceOf(user) > 0

    repay(kashi_pair_0, token, borrower)

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount * (
        before_pps / 10 ** vault.decimals()
    )


def test_borrow_all_with_mixed_distribution(
    chain,
    accounts,
    token,
    vault,
    strategy,
    user,
    strategist,
    amount,
    kashi_pair_0,
    borrower,
    collateral_amount,
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

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount
    assert vault.pricePerShare() >= before_pps

    strategy.adjustKashiPairRatios([5000, 5000, 0, 0], {"from": strategist})

    borrow_all(kashi_pair_0, borrower)

    # withdraw half
    before_pps = vault.pricePerShare()
    vault.withdraw(int(vault.balanceOf(user) * 0.5), {"from": user})
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()

    # The user is only able to make an incomplete withdraw
    vault.withdraw({"from": user})
    assert vault.balanceOf(user) > 0

    repay(kashi_pair_0, token, borrower)

    vault.withdraw({"from": user})
    assert token.balanceOf(user) > amount


def test_borrow_all_harvest(
    chain,
    accounts,
    token,
    vault,
    strategy,
    user,
    strategist,
    amount,
    kashi_pair_0,
    borrower,
    collateral_amount,
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

    strategy.adjustKashiPairRatios([10000, 0, 0, 0], {"from": strategist})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # Sleep for a while to earn yield
    chain.sleep(360)
    chain.mine(27)

    # Harvest 2: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount
    assert vault.pricePerShare() >= before_pps

    borrow_all(kashi_pair_0, borrower)

    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)
    chain.mine(1)
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()

    repay(kashi_pair_0, token, borrower)

    before_pps = vault.pricePerShare()
    strategy.harvest()
    chain.sleep(3600 * 6)
    chain.mine(1)
    assert vault.pricePerShare() > before_pps


def test_borrow_set_ratios(
    chain,
    accounts,
    token,
    vault,
    strategy,
    user,
    strategist,
    amount,
    kashi_pair_0,
    borrower,
    collateral_amount,
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

    strategy.adjustKashiPairRatios([10000, 0, 0, 0], {"from": strategist})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    borrow_all(kashi_pair_0, borrower)

    strategy.adjustKashiPairRatios([2500, 2500, 2500, 2500], {"from": strategist})
    assert strategy.estimatedTotalAssets() >= amount

    repay(kashi_pair_0, token, borrower)

    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount


def test_multiple_users_and_part_borrowed(
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
    kashi_pair_0,
    borrower,
    collateral_amount,
    RELATIVE_APPROX,
):
    # Deposit to the vault
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})
    assert token.balanceOf(vault.address) == amount

    # Harvest 1: Send funds through the strategy
    chain.sleep(1)
    strategy.harvest({"from": strategist})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.adjustKashiPairRatios([10000, 0, 0, 0], {"from": strategist})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    borrow_all(kashi_pair_0, borrower)

    chain.sleep(1)

    token.approve(vault.address, amount, {"from": user_2})
    vault.deposit(amount_2, {"from": user_2})
    assert token.balanceOf(vault.address) >= amount_2

    # Harvest 2: Realize profit
    chain.sleep(1)
    before_pps = vault.pricePerShare()
    strategy.harvest({"from": strategist})
    profit = token.balanceOf(vault.address)  # Profits go to vault
    assert strategy.estimatedTotalAssets() + profit > amount + amount_2
    assert vault.pricePerShare() >= before_pps

    strategy.adjustKashiPairRatios([9700, 100, 100, 100], {"from": strategist})
    assert strategy.estimatedTotalAssets() >= amount + amount_2

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user_2})
    assert pytest.approx(token.balanceOf(user_2), rel=RELATIVE_APPROX) == amount_2 * (
        before_pps / 10 ** vault.decimals()
    )
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()

    # Sleep for a while to earn yield
    chain.sleep(360)
    chain.mine(27)

    # Harvest 3: Realize profit
    before_pps = vault.pricePerShare()
    strategy.harvest({"from": strategist})
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    assert vault.pricePerShare() >= before_pps

    repay(kashi_pair_0, token, borrower)

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount * (
        before_pps / 10 ** vault.decimals()
    )

    # # Harvest 4: Realize profit
    # before_pps = vault.pricePerShare()
    # strategy.harvest({"from": strategist})
    # chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    # chain.mine(1)
    # assert vault.pricePerShare() >= before_pps


def test_remove_kashi_pair_all_borrowed(
    chain,
    token,
    vault,
    strategy,
    amount,
    gov,
    user,
    kashi_pairs,
    kashi_pair_0,
    borrower,
    collateral_amount,
    RELATIVE_APPROX,
):
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": user})
    vault.deposit(amount, {"from": user})

    chain.sleep(1)
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.adjustKashiPairRatios([10000, 0, 0, 0])
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    borrow_all(kashi_pair_0, borrower)

    with brownie.reverts():
        strategy.removeKashiPair(kashi_pair_0, 0, False, {"from": gov})
    strategy.removeKashiPair(kashi_pair_0, 0, True, {"from": gov})
    assert strategy.kashiPairs(0)[0] != kashi_pair_0.address
    assert strategy.estimatedTotalAssets() < amount

    repay(kashi_pair_0, token, borrower)


def borrow_all(kashi_pair_0, borrower):
    borrow_amount = kashi_pair_0.totalAsset().dict()["elastic"]
    return kashi_pair_0.borrow(
        borrower, borrow_amount, {"from": borrower}
    ).return_value[0]


def repay(kashi_pair_0, token, borrower):
    bento_box = Contract(kashi_pair_0.bentoBox())
    bento_box.transfer(
        token,
        borrower,
        kashi_pair_0,
        bento_box.balanceOf(token, borrower),
        {"from": borrower},
    )
    kashi_pair_0.repay(
        borrower,
        True,
        int(kashi_pair_0.userBorrowPart(borrower) * 0.99),
        {"from": borrower},
    )
