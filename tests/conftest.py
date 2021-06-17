import pytest
from brownie import config
from brownie import Contract


@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@pytest.fixture(scope="session")
def gov(accounts):
    yield accounts.at("0xfB8E20c22f8B58D0BDeAbe62Fb8EE2A56DbD73b2", force=True)


@pytest.fixture(scope="session")
def user(accounts):
    yield accounts[0]


@pytest.fixture(scope="session")
def rewards(accounts):
    yield accounts[1]


@pytest.fixture(scope="session")
def guardian(accounts):
    yield accounts[2]


@pytest.fixture(scope="session")
def management(accounts):
    yield accounts[3]


@pytest.fixture(scope="session")
def strategist(accounts):
    yield accounts[4]


@pytest.fixture(scope="session")
def keeper(accounts):
    yield accounts[5]


@pytest.fixture(scope="session")
def user_2(accounts):
    yield accounts[6]


@pytest.fixture(scope="session")
def token():
    token_address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    yield Contract(token_address)


@pytest.fixture(scope="session")
def reserve(accounts):
    yield accounts.at("0x0A59649758aa4d66E25f08Dd01271e891fe52199", force=True)


@pytest.fixture(scope="function")
def amount(accounts, reserve, token, user):
    amount = 10_000 * 10 ** token.decimals()
    token.transfer(user, amount, {"from": reserve})

    yield amount

    if token.balanceOf(user) > 0:
        token.transfer(reserve, token.balanceOf(user), {"from": user})
        assert token.balanceOf(user) == 0


@pytest.fixture(scope="function")
def amount_2(accounts, reserve, token, user_2):
    amount_2 = 2_500 * 10 ** token.decimals()
    token.transfer(user_2, amount_2, {"from": reserve})

    yield amount_2

    if token.balanceOf(user_2) > 0:
        token.transfer(reserve, token.balanceOf(user_2), {"from": user_2})
        assert token.balanceOf(user_2) == 0


@pytest.fixture(scope="session")
def weth():
    token_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    yield Contract(token_address)


@pytest.fixture(scope="session")
def kashi_pair_0():
    yield Contract("0x6EAFe077df3AD19Ade1CE1abDf8bdf2133704f89")  # pid 247


@pytest.fixture(scope="session")
def kashi_pair_1():
    yield Contract("0x4f68e70e3a5308d759961643AfcadfC6f74B30f4")  # pid 198


@pytest.fixture(scope="session")
def kashi_pair_2():
    yield Contract("0xa898974410F7e7689bb626B41BC2292c6A0f5694")  # pid 225


@pytest.fixture(scope="session")
def kashi_pair_3():
    yield Contract("0x65089e337109CA4caFF78b97d40453D37F9d23f8")  # pid 222


@pytest.fixture(scope="session")
def pid_0():
    yield 247


@pytest.fixture(scope="session")
def pid_1():
    yield 198


@pytest.fixture(scope="session")
def pid_2():
    yield 225


@pytest.fixture(scope="session")
def pid_3():
    yield 222


@pytest.fixture(scope="session")
def kashi_pairs(kashi_pair_0, kashi_pair_1, kashi_pair_2, kashi_pair_3):
    yield [kashi_pair_0, kashi_pair_1, kashi_pair_2, kashi_pair_3]


@pytest.fixture(scope="session")
def pids(pid_0, pid_1, pid_2, pid_3):
    yield [pid_0, pid_1, pid_2, pid_3]


@pytest.fixture(scope="session")
def bento_box(kashi_pair_0):
    yield Contract(kashi_pair_0.bentoBox())


@pytest.fixture
def weth_amout(user, weth):
    weth_amout = 10 ** weth.decimals()
    user.transfer(weth, weth_amout)
    yield weth_amout


@pytest.fixture(scope="function")
def vault(pm, gov, rewards, guardian, management, token):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, "", "", guardian, management)
    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagementFee(0, {"from": gov})
    vault.setManagement(management, {"from": gov})
    yield vault


@pytest.fixture(scope="function")
def strategy(strategist, keeper, vault, Strategy, gov, kashi_pairs, bento_box, pids):
    strategy = strategist.deploy(Strategy, vault, bento_box, kashi_pairs, pids)
    strategy.setKeeper(keeper)
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy


@pytest.fixture(scope="session")
def borrower(accounts):
    yield accounts[7]


@pytest.fixture(scope="session")
def collateral():
    yield Contract("0x8798249c2E607446EfB7Ad49eC89dD1865Ff4272")  # xSushi


@pytest.fixture(scope="session")
def collateral_whale(accounts):
    yield accounts.at("0xF256CC7847E919FAc9B808cC216cAc87CCF2f47a", force=True)


@pytest.fixture(scope="function")
def collateral_amount(borrower, collateral, collateral_whale, bento_box, kashi_pair_0):
    collateral_amount = 10_000_000 * 10 ** collateral.decimals()
    collateral.transfer(borrower, collateral_amount, {"from": collateral_whale})

    collateral.approve(bento_box, 2 ** 256 - 1, {"from": borrower})
    bento_box.deposit(
        collateral, borrower, borrower, collateral_amount, 0, {"from": borrower}
    )
    bento_box.transfer(
        collateral, borrower, kashi_pair_0, collateral_amount, {"from": borrower}
    )
    kashi_pair_0.addCollateral(borrower, True, collateral_amount, {"from": borrower})
    yield collateral_amount


@pytest.fixture(scope="session")
def sushi():
    yield Contract("0x6B3595068778DD592e39A122f4f5a5cF09C90fE2")


@pytest.fixture(scope="session")
def sushi_whale(accounts):
    yield accounts.at("0x8798249c2e607446efb7ad49ec89dd1865ff4272", force=True)


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
