import brownie
from brownie import Contract
import pytest


def test_borrow_all(
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

    part_borrowed = borrow_all(kashi_pair_0, borrower)

    with brownie.reverts():
        vault.withdraw({"from": user})

    repay(kashi_pair_0, token, borrower, part_borrowed)

    before_pps = vault.pricePerShare()
    vault.withdraw({"from": user})
    assert pytest.approx(token.balanceOf(user), rel=RELATIVE_APPROX) == amount * (
        before_pps / 10 ** vault.decimals()
    )
    assert pytest.approx(before_pps, rel=RELATIVE_APPROX) == vault.pricePerShare()


def borrow_all(kashi_pair_0, borrower):
    borrow_amount = kashi_pair_0.totalAsset().dict()["elastic"]
    return kashi_pair_0.borrow(
        borrower, borrow_amount, {"from": borrower}
    ).return_value[0]


def repay(kashi_pair_0, token, borrower, part):
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
