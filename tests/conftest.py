import pytest
from brownie import config
from brownie import Contract


@pytest.fixture
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
    token_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    yield Contract(token_address)


@pytest.fixture
def reserve(accounts):
    yield accounts.at("0x1a13F4Ca1d028320A707D99520AbFefca3998b7F", force=True)


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
def kashi_pair_0():
    yield Contract("0xe4b3c431E29B15978556f55b2cd046Be614F558D")


@pytest.fixture
def kashi_pair_1():
    yield Contract("0xd51B929792Cfcde30f2619e50E91513dCeC89B23")


@pytest.fixture
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
def strategy(strategist, keeper, vault, Strategy, gov, kashi_pair_0, kashi_pair_1, bento_box):
    strategy = strategist.deploy(Strategy, vault, bento_box, [kashi_pair_0])
    strategy.setKeeper(keeper)
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
