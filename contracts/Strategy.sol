// SPDX-License-Identifier: AGPL-3.0

pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import {
    BaseStrategy,
    StrategyParams
} from "@yearnvaults/contracts/BaseStrategy.sol";
import {
    SafeERC20,
    SafeMath,
    IERC20,
    Address
} from "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";
import "@openzeppelin/contracts/math/Math.sol";

import {IKashiPair} from "./sushiswap/kashi-lending/interfaces/IKashiPair.sol";
import {
    IBentoBoxV1 as IBentoBox
} from "./sushiswap/bentobox-sdk/contracts/IBentoBoxV1.sol";
import {
    Rebase,
    RebaseLibrary
} from "./boringcrypto/boring-solidity/libraries/BoringRebase.sol";
import {BIERC20} from "./boringcrypto/boring-solidity/interfaces/IERC20.sol";
import "./sushiswap/sushiswap/interfaces/IMasterChef.sol";
import "./uniswapv2/interfaces/IUniswapV2Router02.sol";

contract Strategy is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;
    using RebaseLibrary for Rebase;

    struct KashiPairInfo {
        IKashiPair kashiPair;
        uint256 pid;
    }

    bool internal isOriginal = true;
    uint256 internal constant MAX_PAIRS = 5;
    uint256 internal constant MAX_BPS = 10_000;

    address internal constant DEFAULT_SUSHI_ROUTER =
        0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F;

    IERC20 internal constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IERC20 internal constant sushi =
        IERC20(0x6B3595068778DD592e39A122f4f5a5cF09C90fE2);
    IMasterChef internal constant masterChef =
        IMasterChef(0xc2EdaD668740f1aA35E4D8f227fB8E17dcA888Cd);

    IBentoBox public bentoBox;
    KashiPairInfo[] public kashiPairs;
    IUniswapV2Router02 public sushiRouter;

    uint256 public dustThreshold = 2;

    // Path for swaps
    address[] private path;

    constructor(
        address _vault,
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids
    ) public BaseStrategy(_vault) {
        _initializeStrat(_bentoBox, _kashiPairs, _pids);
    }

    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        _initializeStrat(_bentoBox, _kashiPairs, _pids);
    }

    event Cloned(address indexed clone);

    function cloneKashiLender(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids
    ) external returns (address newStrategy) {
        require(isOriginal);
        // Copied from https://github.com/optionality/clone-factory/blob/master/contracts/CloneFactory.sol
        bytes20 addressBytes = bytes20(address(this));
        assembly {
            // EIP-1167 bytecode
            let clone_code := mload(0x40)
            mstore(
                clone_code,
                0x3d602d80600a3d3981f3363d3d373d3d3d363d73000000000000000000000000
            )
            mstore(add(clone_code, 0x14), addressBytes)
            mstore(
                add(clone_code, 0x28),
                0x5af43d82803e903d91602b57fd5bf30000000000000000000000000000000000
            )
            newStrategy := create(0, clone_code, 0x37)
        }

        Strategy(newStrategy).initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _bentoBox,
            _kashiPairs,
            _pids
        );

        emit Cloned(newStrategy);
    }

    function _initializeStrat(
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids
    ) internal {
        require(address(bentoBox) == address(0)); // Check if previously initialized
        require(_kashiPairs.length <= MAX_PAIRS); // Must not exceed the max length
        require(_kashiPairs.length == _pids.length); // Pairs length must match pids length

        sushiRouter = IUniswapV2Router02(DEFAULT_SUSHI_ROUTER);

        bentoBox = IBentoBox(_bentoBox);

        for (uint256 i = 0; i < _kashiPairs.length; i++) {
            kashiPairs.push(
                KashiPairInfo(IKashiPair(_kashiPairs[i]), _pids[i])
            );
            // kashiPair must use the right bentoBox
            require(address(kashiPairs[i].kashiPair.bentoBox()) == _bentoBox);
            // kashiPair asset must match want
            require(address(kashiPairs[i].kashiPair.asset()) == address(want));

            if (_pids[i] != 0) {
                // the masterChef pid token must match the kashiPair
                require(
                    address(masterChef.poolInfo(_pids[i]).lpToken) ==
                        _kashiPairs[i]
                );

                IERC20(_kashiPairs[i]).safeApprove(
                    address(masterChef),
                    type(uint256).max
                );
            }
        }

        want.safeApprove(_bentoBox, type(uint256).max);
        sushi.safeApprove(address(sushiRouter), type(uint256).max);

        // Initialize the swap path
        path = new address[](3);
        path[0] = address(sushi);
        path[1] = address(weth);
        path[2] = address(want);
    }

    function name() external view override returns (string memory) {
        return "StrategyKashiMultiPairLender";
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        uint256 totalShares = sharesInBento();

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            totalShares = totalShares.add(
                kashiFractionToBentoShares(
                    kashiPairs[i].kashiPair,
                    kashiFractionTotal(i),
                    true
                )
            );
        }

        return balanceOfWant().add(bentoSharesToWant(totalShares, true));
    }

    function kashiPairEstimatedAssets(uint256 i) public view returns (uint256) {
        return
            bentoSharesToWant(
                kashiFractionToBentoShares(
                    kashiPairs[i].kashiPair,
                    kashiFractionTotal(i),
                    true
                ),
                true
            );
    }

    function prepareReturn(uint256 _debtOutstanding)
        internal
        override
        returns (
            uint256 _profit,
            uint256 _loss,
            uint256 _debtPayment
        )
    {
        for (uint256 i = 0; i < kashiPairs.length; i++) {
            accrueInterest(i);

            // Claim masterchef rewards
            if (kashiPairs[i].pid != 0) {
                masterChef.deposit(kashiPairs[i].pid, 0);
            }
        }

        sell();

        uint256 assets = estimatedTotalAssets();
        uint256 wantBal = balanceOfWant();

        uint256 debt = vault.strategies(address(this)).totalDebt;

        if (assets >= debt) {
            _profit = assets.sub(debt);
        } else {
            _loss = debt.sub(assets);
        }

        _debtPayment = _debtOutstanding;
        uint256 amountToFree = _debtPayment.add(_profit);

        if (amountToFree > 0 && wantBal < amountToFree) {
            liquidatePosition(amountToFree.sub(wantBal));

            uint256 newLoose = balanceOfWant();

            // if we didnt free enough money, prioritize paying down debt before taking profit
            if (newLoose < amountToFree) {
                if (newLoose <= _debtPayment) {
                    _profit = 0;
                    _debtPayment = newLoose;
                } else {
                    _profit = newLoose.sub(_debtPayment);
                }
            }
        }
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        if (emergencyExit) {
            return;
        }

        uint256 wantBalance = balanceOfWant();

        uint256 shares = 0;

        if (wantBalance > dustThreshold) {
            (, shares) = bentoBox.deposit(
                BIERC20(address(want)),
                address(this),
                address(this),
                wantBalance,
                0 // setting this to 0 lets the previous argument determine the wantBalance size
            );
        }

        uint256 sharesInBento = sharesInBento();

        if (sharesInBento > wantToBentoShares(dustThreshold, false)) {
            // Get highest interest rate pair
            uint256 highestInterestIndex = highestInterestPairIndex();

            depositInKashiPair(highestInterestIndex, sharesInBento);
        }
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 wantBalance = balanceOfWant();
        if (_amountNeeded > wantBalance) {
            uint256 amountToFree = _amountNeeded.sub(wantBalance);

            uint256 deposited = estimatedTotalAssets().sub(wantBalance);

            if (deposited < amountToFree) {
                amountToFree = deposited;
            }
            if (amountToFree > 0) {
                uint256 sharesNeeded = wantToBentoShares(amountToFree, true);
                uint256 bentoShares = sharesInBento();

                uint256 sharesToFreeFromKashi =
                    bentoShares <= sharesNeeded
                        ? sharesNeeded.sub(bentoShares)
                        : 0;

                uint256 sharesFreedFromKashi = 0;

                // Find the lowest apr pair with at least the lesser of
                //   - the amount to free
                //   - the ratio of total assets to number of pairs
                uint256 lowestInterestIndex =
                    lowestInterestPairIndex(
                        Math.min(
                            sharesToFreeFromKashi,
                            wantToBentoShares(
                                estimatedTotalAssets().div(kashiPairs.length),
                                true
                            )
                        )
                    );
                if (lowestInterestIndex != type(uint256).max) {
                    sharesFreedFromKashi = liquidateKashiPair(
                        lowestInterestIndex,
                        sharesToFreeFromKashi
                    );
                }

                for (
                    uint256 i = 0;
                    i < kashiPairs.length &&
                        sharesToFreeFromKashi > sharesFreedFromKashi;
                    i++
                ) {
                    if (i == lowestInterestIndex) continue; // we already visited this

                    sharesFreedFromKashi = sharesFreedFromKashi.add(
                        liquidateKashiPair(
                            i,
                            sharesToFreeFromKashi.sub(sharesFreedFromKashi)
                        )
                    );
                }

                bentoBox.withdraw(
                    BIERC20(address(want)),
                    address(this),
                    address(this),
                    0,
                    sharesInBento()
                );
            }

            _liquidatedAmount = balanceOfWant();

            if (_amountNeeded > _liquidatedAmount) {
                _loss = _amountNeeded.sub(_liquidatedAmount);
            }
        } else {
            _liquidatedAmount = _amountNeeded;
        }
    }

    function liquidateAllPositions()
        internal
        override
        returns (uint256 _liquidatedAmount)
    {
        (_liquidatedAmount, ) = liquidatePosition(type(uint256).max);
    }

    // We stake in the masterChef so we can't transfer assets when migrating
    function prepareMigration(address _newStrategy) internal override {}

    function addKashiPair(address _newKashiPair, uint256 _newPid)
        external
        onlyGovernance
    {
        // cannot exceed max pair length
        require(kashiPairs.length < MAX_PAIRS);
        // must use the correct bentobox
        require(
            address(IKashiPair(_newKashiPair).bentoBox()) == address(bentoBox)
        );
        // kashPair asset must match want
        require(IKashiPair(_newKashiPair).asset() == BIERC20(address(want)));
        if (_newPid != 0) {
            // masterChef pid token must match the kashiPair
            require(
                address(masterChef.poolInfo(_newPid).lpToken) == _newKashiPair
            );
        }

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            // kashiPair must not already be attached
            require(_newKashiPair != address(kashiPairs[i].kashiPair));
        }

        kashiPairs.push(KashiPairInfo(IKashiPair(_newKashiPair), _newPid));

        if (_newPid != 0) {
            IERC20(_newKashiPair).safeApprove(
                address(masterChef),
                type(uint256).max
            );
        }
    }

    function removeKashiPair(address _remKashiPair)
        external
        onlyEmergencyAuthorized
    {
        for (uint256 i = 0; i < kashiPairs.length; i++) {
            if (_remKashiPair != address(kashiPairs[i].kashiPair)) continue;
            liquidateKashiPair(
                i,
                wantToBentoShares(estimatedTotalAssets(), true)
            );
            if (kashiPairs[i].pid != 0) {
                IERC20(_remKashiPair).safeApprove(address(masterChef), 0);
            }
            kashiPairs[i] = kashiPairs[kashiPairs.length - 1];
            kashiPairs.pop();
            return;
        }

        revert("kashiPair not found");
    }

    function adjustKashiPairRatios(uint256[] calldata _ratios)
        external
        onlyAuthorized
    {
        // length of ratios must match number of pairs
        require(_ratios.length == kashiPairs.length);

        uint256 totalRatio;

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            // We must accrue all pairs to ensure we get an accurate estimate of assets
            accrueInterest(i);
            totalRatio += _ratios[i];
        }

        require(totalRatio == MAX_BPS); //ratios must add to 10000 bps

        uint256 wantBalance = balanceOfWant();
        if (wantBalance > dustThreshold) {
            bentoBox.deposit(
                BIERC20(address(want)),
                address(this),
                address(this),
                wantBalance,
                0 // setting this to 0, let's the previous argument determine the deposit size
            );
        }

        uint256 totalAssets = estimatedTotalAssets();
        uint256[] memory kashiPairsIncreasedAllocation =
            new uint256[](kashiPairs.length);

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            uint256 pairTotalAssets =
                bentoSharesToWant(
                    kashiFractionToBentoShares(
                        kashiPairs[i].kashiPair,
                        kashiFractionTotal(i),
                        true
                    ),
                    true
                );
            uint256 targetAssets = (_ratios[i] * totalAssets) / MAX_BPS;
            if (targetAssets < pairTotalAssets) {
                uint256 toLiquidate = pairTotalAssets.sub(targetAssets);
                liquidateKashiPair(i, wantToBentoShares(toLiquidate, true));
            } else if (targetAssets > pairTotalAssets) {
                kashiPairsIncreasedAllocation[i] = targetAssets.sub(
                    pairTotalAssets
                );
            }
        }

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            if (kashiPairsIncreasedAllocation[i] == 0) continue;

            uint256 sharesInBento = sharesInBento();
            uint256 sharesToAdd =
                wantToBentoShares(kashiPairsIncreasedAllocation[i], true);

            if (sharesToAdd > sharesInBento) {
                sharesToAdd = sharesInBento;
            }

            depositInKashiPair(i, sharesToAdd);
        }
    }

    function depositInKashiPair(uint256 kashiPairIndex, uint256 sharesToDeposit)
        internal
    {
        bentoBox.transfer(
            BIERC20(address(want)),
            address(this),
            address(kashiPairs[kashiPairIndex].kashiPair),
            sharesToDeposit
        );

        uint256 depositedFraction =
            kashiPairs[kashiPairIndex].kashiPair.addAsset(
                address(this),
                true,
                sharesToDeposit
            );

        if (kashiPairs[kashiPairIndex].pid != 0) {
            masterChef.deposit(
                kashiPairs[kashiPairIndex].pid,
                depositedFraction
            );
        }
    }

    function liquidateKashiPair(uint256 kashiPairIndex, uint256 sharesToFree)
        internal
        returns (uint256 _shareLiquidated)
    {
        // We need to call accrue to accurately calculate totalAssets
        accrueInterest(kashiPairIndex);

        uint256 liquidShares = kashiPairLiquidShares(kashiPairIndex);
        if (sharesToFree > liquidShares) {
            sharesToFree = liquidShares;
        }

        uint256 fractionsToFree =
            bentoSharesToKashiFraction(
                kashiPairs[kashiPairIndex].kashiPair,
                sharesToFree,
                true
            );

        // Remove from masterChef if there is a non-zero pid
        if (kashiPairs[kashiPairIndex].pid != 0) {
            uint256 fractionInMc = kashiFactionInMasterChef(kashiPairIndex);
            uint256 fractionsToFreeFromMc = fractionsToFree;
            if (fractionsToFreeFromMc > fractionInMc) {
                fractionsToFreeFromMc = fractionInMc;
            }
            masterChef.withdraw(
                kashiPairs[kashiPairIndex].pid,
                fractionsToFreeFromMc
            );
        }

        uint256 fractionBalance = kashiFractionInPair(kashiPairIndex);

        if (fractionsToFree > fractionBalance) {
            fractionsToFree = fractionBalance;
        }

        _shareLiquidated = kashiPairs[kashiPairIndex].kashiPair.removeAsset(
            address(this),
            fractionsToFree
        );

        // Redeposit into the masterChef if there's some spare change
        uint256 looseKashiFraction = kashiFractionInPair(kashiPairIndex);
        if (kashiPairs[kashiPairIndex].pid != 0) {
            masterChef.deposit(
                kashiPairs[kashiPairIndex].pid,
                looseKashiFraction
            );
        }
    }

    // sell all function
    function sell() internal {
        uint256 sushiBal = balanceOfSushi();
        if (sushiBal == 0) {
            return;
        }

        sushiRouter.swapExactTokensForTokens(
            sushiBal,
            uint256(0),
            path,
            address(this),
            now
        );
    }

    function accrueInterest(uint256 kashiPairIndex) internal {
        (, uint256 lastAccrued, ) =
            kashiPairs[kashiPairIndex].kashiPair.accrueInfo();
        // Accure interest
        if (block.timestamp > lastAccrued) {
            kashiPairs[kashiPairIndex].kashiPair.accrue();
        }
    }

    function setDustThreshold(uint256 _newDustThreshold)
        external
        onlyAuthorized
    {
        dustThreshold = _newDustThreshold;
    }

    function setPath(address[] calldata _path) external onlyGovernance {
        path = _path;
    }

    function setRouter(address _router) external onlyGovernance {
        sushiRouter = IUniswapV2Router02(_router);
    }

    function balanceOfWant() internal view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function balanceOfSushi() internal view returns (uint256) {
        return sushi.balanceOf(address(this));
    }

    function sharesInBento() internal view returns (uint256) {
        return bentoBox.balanceOf(BIERC20(address(want)), address(this));
    }

    function kashiFractionTotal(uint256 i) internal view returns (uint256) {
        return kashiFactionInMasterChef(i).add(kashiFractionInPair(i));
    }

    function kashiFactionInMasterChef(uint256 i)
        internal
        view
        returns (uint256 _kashiFraction)
    {
        if (kashiPairs[i].pid != 0) {
            _kashiFraction = masterChef
                .userInfo(kashiPairs[i].pid, address(this))
                .amount;
        }
    }

    function kashiFractionInPair(uint256 i) internal view returns (uint256) {
        return kashiPairs[i].kashiPair.balanceOf(address(this));
    }

    function kashiPairLiquidShares(uint256 i) internal view returns (uint256) {
        return kashiPairs[i].kashiPair.totalAsset().elastic;
    }

    function highestInterestPairIndex()
        internal
        view
        returns (uint256 _highestIndex)
    {
        uint256 highestInterest = 0;

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            (uint256 _interestPerBlock, , ) =
                kashiPairs[i].kashiPair.accrueInfo();
            if (_interestPerBlock > highestInterest) {
                highestInterest = _interestPerBlock;
                _highestIndex = i;
            }
        }
    }

    function lowestInterestPairIndex(uint256 minLiquidShares)
        internal
        view
        returns (uint256 _lowestIndex)
    {
        _lowestIndex = type(uint256).max; // Max indicate no low APR with liquidity
        uint256 lowestInterest = type(uint256).max;

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            (uint256 _interestPerBlock, , ) =
                kashiPairs[i].kashiPair.accrueInfo();

            if (
                _interestPerBlock < lowestInterest &&
                kashiFractionTotal(i) > dustThreshold &&
                kashiPairLiquidShares(i) >= minLiquidShares
            ) {
                lowestInterest = _interestPerBlock;
                _lowestIndex = i;
            }
        }
    }

    function wantToBentoShares(uint256 wantAmount, bool roundUp)
        internal
        view
        returns (uint256)
    {
        return bentoBox.toShare(BIERC20(address(this)), wantAmount, roundUp);
    }

    function bentoSharesToWant(uint256 bentoShares, bool roundUp)
        internal
        view
        returns (uint256)
    {
        return bentoBox.toAmount(BIERC20(address(this)), bentoShares, roundUp);
    }

    function bentoSharesToKashiFraction(
        IKashiPair kashiPair,
        uint256 bentoShares,
        bool roundUp
    ) internal view returns (uint256 _kashiFraction) {
        // Adapted from https://github.com/sushiswap/kashi-lending/blob/b6e3521d8628a835935c94a9039cfd192044d66b/contracts/KashiPair.sol#L320-L323
        Rebase memory totalAsset = kashiPair.totalAsset();
        Rebase memory totalBorrow = kashiPair.totalBorrow();
        uint256 allShare =
            uint256(totalAsset.elastic).add(
                wantToBentoShares(totalBorrow.elastic, roundUp)
            );
        _kashiFraction = allShare == 0
            ? bentoShares
            : bentoShares.mul(totalAsset.base).div(allShare);
    }

    function kashiFractionToBentoShares(
        IKashiPair kashiPair,
        uint256 _kashiFraction,
        bool roundUp
    ) internal view returns (uint256 bentoShares) {
        // Adapted from https://github.com/sushiswap/kashi-lending/blob/b6e3521d8628a835935c94a9039cfd192044d66b/contracts/KashiPair.sol#L351-L353
        Rebase memory totalAsset = kashiPair.totalAsset();
        Rebase memory totalBorrow = kashiPair.totalBorrow();
        uint256 allShare =
            uint256(totalAsset.elastic).add(
                wantToBentoShares(totalBorrow.elastic, roundUp)
            );
        bentoShares = _kashiFraction.mul(allShare).div(totalAsset.base);
    }

    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}

    function ethToWant(uint256 _amtInWei)
        public
        view
        virtual
        override
        returns (uint256)
    {
        // TODO create an accurate price oracle
        return _amtInWei;
    }
}
