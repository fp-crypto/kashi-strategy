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

contract Strategy is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;
    using RebaseLibrary for Rebase;

    bool internal isOriginal = true;
    uint256 internal constant maxPairs = 5;

    IBentoBox public bentoBox;
    IKashiPair[] public kashiPairs;

    uint256 public dustThreshold = 2;

    constructor(
        address _vault,
        address _bentoBox,
        address[] memory _kashiPairs
    ) public BaseStrategy(_vault) {
        _initializeStrat(_bentoBox, _kashiPairs);
    }

    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _bentoBox,
        address[] memory _kashiPairs
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        _initializeStrat(_bentoBox, _kashiPairs);
    }

    event Cloned(address indexed clone);

    function cloneKashiLender(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _bentoBox,
        address[] memory _kashiPairs
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
            _kashiPairs
        );

        emit Cloned(newStrategy);
    }

    function _initializeStrat(address _bentoBox, address[] memory _kashiPairs)
        internal
    {
        require(
            address(bentoBox) == address(0),
            "strategy already initialized"
        );
        require(_kashiPairs.length <= maxPairs, "exceeded maxPairs");

        bentoBox = IBentoBox(_bentoBox);

        kashiPairs = new IKashiPair[](_kashiPairs.length);
        for (uint256 i = 0; i < _kashiPairs.length; i++) {
            kashiPairs[i] = IKashiPair(_kashiPairs[i]);
            require(
                address(kashiPairs[i].bentoBox()) == _bentoBox,
                "bento does not match"
            );
            require(
                address(kashiPairs[i].asset()) == address(want),
                "asset does not match want"
            );
        }

        want.safeApprove(_bentoBox, type(uint256).max);
    }

    function name() external view override returns (string memory) {
        return string(abi.encodePacked("StrategyKashiLender"));
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        uint256 totalShares = sharesInBento();

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            totalShares = totalShares.add(
                kashiFractionToBentoShares(
                    kashiPairs[i],
                    kashiFraction(i),
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
                    kashiPairs[i],
                    kashiFraction(i),
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
            (, uint256 lastAccrued, ) = kashiPairs[i].accrueInfo();
            if (block.timestamp > lastAccrued) {
                kashiPairs[i].accrue();
            }
        }

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
                0 // setting this to 0, let's the previous argument determine the deposit size
            );
        }

        uint256 sharesInBento = sharesInBento();

        if (sharesInBento > wantToBentoShares(dustThreshold, false)) {
            // Get highest interest rate pair
            (IKashiPair kashiPair, ) = highestAndLowestInterestPairs();

            depositInKashiPair(kashiPair, sharesInBento);
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

                for (
                    uint256 i = 0;
                    i < kashiPairs.length &&
                        sharesToFreeFromKashi > sharesFreedFromKashi;
                    i++
                ) {
                    // get the lowest interest pair
                    (, IKashiPair kashiPair) = highestAndLowestInterestPairs();
                    if (address(kashiPair) == address(0)) {
                        // break if there is no lowest interest pair
                        break;
                    }
                    sharesFreedFromKashi = sharesFreedFromKashi.add(
                        liquidateKashiPair(
                            kashiPair,
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

    // The _newStrategy must support the same kashiPairs or bad things will happen
    function prepareMigration(address _newStrategy) internal override {
        for (uint256 i = 0; i < kashiPairs.length; i++) {
            kashiPairs[i].transfer(_newStrategy, kashiFraction(i));
        }
    }

    function addKashiPair(address _newKashiPair) external onlyGovernance {
        require(
            address(IKashiPair(_newKashiPair).bentoBox()) == address(bentoBox),
            "BentoBox does not match"
        );
        require(
            IKashiPair(_newKashiPair).asset() == BIERC20(address(want)),
            "KashiPair asset does not match want"
        );

        kashiPairs.push(IKashiPair(_newKashiPair));
    }

    function removeKashiPair(address _remKashiPair) external onlyGovernance {
        for (uint256 i = 0; i < kashiPairs.length; i++) {
            if (_remKashiPair != address(kashiPairs[i])) continue;
            liquidateKashiPair(
                kashiPairs[i],
                wantToBentoShares(estimatedTotalAssets(), true)
            );
            kashiPairs[i] = kashiPairs[kashiPairs.length - 1];
            kashiPairs.pop();
            return;
        }

        revert("kashiPair not found");
    }

    function adjustKashiPairRatios(uint256[] memory _ratios)
        external
        onlyAuthorized
    {
        for (uint256 i = 0; i < kashiPairs.length; i++) {
            kashiPairs[i].accrue();
        }

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
                        kashiPairs[i],
                        kashiFraction(i),
                        true
                    ),
                    true
                );
            uint256 targetAssets = (_ratios[i] * totalAssets) / 10**4;
            if (targetAssets < pairTotalAssets) {
                uint256 toLiquidate = pairTotalAssets.sub(targetAssets);
                liquidateKashiPair(
                    kashiPairs[i],
                    wantToBentoShares(toLiquidate, true)
                );
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

            depositInKashiPair(kashiPairs[i], sharesToAdd);
        }
    }

    function depositInKashiPair(IKashiPair kashiPair, uint256 sharesToDeposit)
        internal
    {
        bentoBox.transfer(
            BIERC20(address(want)),
            address(this),
            address(kashiPair),
            sharesToDeposit
        );

        kashiPair.addAsset(address(this), true, sharesToDeposit);
    }

    function liquidateKashiPair(IKashiPair kashiPair, uint256 sharesToFree)
        internal
        returns (uint256 _shareLiquiduated)
    {
        (, uint256 lastAccrued, ) = kashiPair.accrueInfo();
        if (block.timestamp > lastAccrued) {
            // We need to call accrue to accurately calculate totalAssets
            kashiPair.accrue();
        }

        uint256 fractionBalance = kashiPair.balanceOf(address(this));
        uint256 fractionsToFree =
            bentoSharesToKashiFraction(kashiPair, sharesToFree, true);
        if (fractionsToFree > fractionBalance) {
            fractionsToFree = fractionBalance;
        }

        _shareLiquiduated = kashiPair.removeAsset(
            address(this),
            fractionsToFree
        );
    }

    function setDustThreshold(uint256 _newDustThreshold)
        external
        onlyAuthorized
    {
        dustThreshold = _newDustThreshold;
    }

    function balanceOfWant() internal view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function sharesInBento() internal view returns (uint256) {
        return bentoBox.balanceOf(BIERC20(address(want)), address(this));
    }

    function kashiFraction(uint256 i) internal view returns (uint256) {
        return kashiPairs[i].balanceOf(address(this));
    }

    function highestAndLowestInterestPairs()
        internal
        view
        returns (IKashiPair _highest, IKashiPair _lowest)
    {
        uint256 highestInterest = 0;
        uint256 lowestInterest = type(uint256).max;

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            (uint256 _interestPerBlock, , ) = kashiPairs[i].accrueInfo();
            // getSushiPerBlock
            // router.swap

            if (_interestPerBlock > highestInterest) {
                highestInterest = _interestPerBlock;
                _highest = kashiPairs[i];
            }
            if (
                _interestPerBlock < lowestInterest &&
                kashiFraction(i) > dustThreshold
            ) {
                lowestInterest = _interestPerBlock;
                _lowest = kashiPairs[i];
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
