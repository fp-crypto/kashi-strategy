import pytest
from brownie import config
from brownie import Contract


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
    amount = 250_000 * 10 ** token.decimals()
    token.transfer(user, amount, {"from": reserve})

    yield amount

    if token.balanceOf(user) > 0:
        token.transfer(reserve, token.balanceOf(user), {"from": user})
        assert token.balanceOf(user) == 0


@pytest.fixture(scope="function")
def amount_2(accounts, reserve, token, user_2):
    amount_2 = 50_000 * 10 ** token.decimals()
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
    yield Contract("0x6EAFe077df3AD19Ade1CE1abDf8bdf2133704f89")


@pytest.fixture(scope="session")
def kashi_pair_1():
    yield Contract("0x4f68e70e3a5308d759961643AfcadfC6f74B30f4")


@pytest.fixture(scope="session")
def kashi_pairs(kashi_pair_0, kashi_pair_1):
    yield [kashi_pair_0, kashi_pair_1]


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
def strategy(strategist, keeper, vault, Strategy, gov, kashi_pairs, bento_box):
    strategy = strategist.deploy(Strategy, vault, bento_box, kashi_pairs)
    strategy.setKeeper(keeper)
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
