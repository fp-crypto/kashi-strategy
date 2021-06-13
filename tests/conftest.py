import pytest
from brownie import config
from brownie import Contract


@pytest.fixture
def gov(accounts):
    yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)


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
    token_address = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
    yield Contract(token_address)


@pytest.fixture
def reserve(accounts):
    yield accounts.at("0xF977814e90dA44bFA03b6295A0616a897441aceC", force=True)


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


@pytest.fixture
def weth():
    token_address = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
    yield Contract(token_address)


@pytest.fixture
def kashi_pair():
    kashi_pair = "0xe9E73d71eD122c7b5c9DC3c5087645eaD294A11D"
    yield Contract(kashi_pair)


@pytest.fixture
def bento_box(kashi_pair):
    yield Contract(kashi_pair.bentoBox())


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
def strategy(strategist, keeper, vault, Strategy, gov, kashi_pair, bento_box):
    strategy = strategist.deploy(Strategy, vault, bento_box, [kashi_pair])
    strategy.setKeeper(keeper)
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
