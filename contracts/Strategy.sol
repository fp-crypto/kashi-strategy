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
    uint256 internal constant MAX_BPS = 1e4;

    // Kashi constants (apply to MediumRiskPairs)
    uint256 internal constant KASHI_MINIMUM_TARGET_UTILIZATION = 7e17; // 70%
    uint256 internal constant KASHI_MAXIMUM_TARGET_UTILIZATION = 8e17; // 80%
    uint256 internal constant KASHI_UTILIZATION_PRECISION = 1e18;

    IERC20 internal constant weth =
        IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    IERC20 internal constant sushi =
        IERC20(0x6B3595068778DD592e39A122f4f5a5cF09C90fE2);

    IMasterChef public constant masterChef =
        IMasterChef(0xc2EdaD668740f1aA35E4D8f227fB8E17dcA888Cd);
    IUniswapV2Router02 public constant sushiRouter =
        IUniswapV2Router02(0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F);

    IBentoBox public bentoBox;
    KashiPairInfo[] public kashiPairs;

    uint256 public dustThreshold = 2;

    // Path for swaps
    address[] private path;

    string private strategyName;

    constructor(
        address _vault,
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids,
        string memory _strategyName
    ) public BaseStrategy(_vault) {
        _initializeStrat(_bentoBox, _kashiPairs, _pids, _strategyName);
    }

    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids,
        string memory _strategyName
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        _initializeStrat(_bentoBox, _kashiPairs, _pids, _strategyName);
    }

    event Cloned(address indexed clone);

    function cloneKashiLender(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids,
        string memory _strategyName
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
            _pids,
            _strategyName
        );

        emit Cloned(newStrategy);
    }

    function _initializeStrat(
        address _bentoBox,
        address[] memory _kashiPairs,
        uint256[] memory _pids,
        string memory _strategyName
    ) internal {
        require(address(bentoBox) == address(0)); // Check if previously initialized
        require(_kashiPairs.length <= MAX_PAIRS); // Must not exceed the max length
        require(_kashiPairs.length == _pids.length); // Pairs length must match pids length

        strategyName = bytes(_strategyName).length == 0
            ? "StrategyKashiMultiPairLender"
            : _strategyName;

        bentoBox = IBentoBox(_bentoBox);

        healthCheck = address(0xDDCea799fF1699e98EDF118e0629A974Df7DF012); // health.ychad.eth

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
        return strategyName;
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        uint256 totalShares = sharesInBento();

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            KashiPairInfo memory kashiPairInfo = kashiPairs[i];

            totalShares = totalShares.add(
                kashiFractionToBentoShares(
                    kashiPairInfo.kashiPair,
                    kashiFractionTotal(
                        kashiPairInfo.kashiPair,
                        kashiPairInfo.pid
                    )
                )
            );
        }

        return balanceOfWant().add(bentoSharesToWant(totalShares));
    }

    function kashiPairEstimatedAssets(uint256 i) public view returns (uint256) {
        KashiPairInfo memory kashiPairInfo = kashiPairs[i];

        return
            bentoSharesToWant(
                kashiFractionToBentoShares(
                    kashiPairInfo.kashiPair,
                    kashiFractionTotal(
                        kashiPairInfo.kashiPair,
                        kashiPairInfo.pid
                    )
                )
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
            KashiPairInfo memory kashiPairInfo = kashiPairs[i];
            if (
                kashiFractionTotal(
                    kashiPairInfo.kashiPair,
                    kashiPairInfo.pid
                ) == 0
            ) continue; // skip the pair has no assets
            accrueInterest(kashiPairInfo.kashiPair);
            depositKashiInMasterChef(
                kashiPairInfo.kashiPair,
                kashiPairInfo.pid
            ); // claim and deposit loose
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
            (uint256 newLoose, ) = liquidatePosition(amountToFree);

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
            (, shares) = depositInBento(wantBalance);
        }

        uint256 sharesInBento = sharesInBento();

        if (sharesInBento > wantToBentoShares(dustThreshold)) {
            // Get highest interest rate pair
            (IKashiPair highestPair, uint256 highestPid) =
                highestInterestPair(sharesInBento);

            depositInKashiPair(highestPair, highestPid, sharesInBento);
        }
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 wantBalance = balanceOfWant();

        if (_amountNeeded <= wantBalance) {
            return (_amountNeeded, 0);
        }

        uint256 amountToFree = _amountNeeded.sub(wantBalance);
        uint256 deposited = estimatedTotalAssets().sub(wantBalance);

        if (amountToFree.add(dustThreshold) > deposited) {
            amountToFree = deposited;
        }

        if (amountToFree > 0) {
            uint256 sharesNeeded = wantToBentoShares(amountToFree);
            uint256 bentoShares = sharesInBento();

            if (sharesNeeded > bentoShares) {
                uint256 sharesToFreeFromKashi = sharesNeeded.sub(bentoShares);
                uint256 sharesFreedFromKashi = 0;

                // Find the lowest apr pair with at least the lesser of
                //   - the amount to free
                //   - the mean assets per pair
                (IKashiPair lowestPair, uint256 lowestPid) =
                    lowestInterestPair(
                        Math.min(
                            sharesToFreeFromKashi,
                            wantToBentoShares(
                                estimatedTotalAssets().div(kashiPairs.length)
                            )
                        )
                    );
                if (address(lowestPair) != address(0)) {
                    sharesFreedFromKashi = liquidateKashiPair(
                        lowestPair,
                        lowestPid,
                        sharesToFreeFromKashi
                    );
                }

                for (
                    uint256 i = 0;
                    i < kashiPairs.length &&
                        sharesFreedFromKashi.add(dustThreshold) <
                        sharesToFreeFromKashi;
                    i++
                ) {
                    KashiPairInfo memory kashiPairInfo = kashiPairs[i];

                    if (address(kashiPairInfo.kashiPair) == address(lowestPair))
                        continue; // we already visited this

                    sharesFreedFromKashi = sharesFreedFromKashi.add(
                        liquidateKashiPair(
                            kashiPairInfo.kashiPair,
                            kashiPairInfo.pid,
                            sharesToFreeFromKashi.sub(sharesFreedFromKashi)
                        )
                    );
                }
            }

            bentoBox.withdraw(
                BIERC20(address(want)),
                address(this),
                address(this),
                0,
                sharesInBento()
            );
        }

        _liquidatedAmount = Math.min(balanceOfWant(), _amountNeeded);

        // To prevent the vault from moving on to the next strategy in the queue
        // when we return the amountRequested minus dust, take a dust sized loss
        if (_liquidatedAmount < _amountNeeded) {
            uint256 diff = _amountNeeded.sub(_liquidatedAmount);
            if (diff <= dustThreshold) {
                _loss = diff;
            }
        }
    }

    function liquidateAllPositions()
        internal
        override
        returns (uint256 _liquidatedAmount)
    {
        (_liquidatedAmount, ) = liquidatePosition(estimatedTotalAssets());
    }

    // new strategy **must** have the same kashiPairs attached
    function prepareMigration(address _newStrategy) internal override {
        for (uint256 i = 0; i < kashiPairs.length; i++) {
            KashiPairInfo memory kashiPairInfo = kashiPairs[i];

            if (kashiPairInfo.pid != 0) {
                masterChef.withdraw(
                    kashiPairInfo.pid,
                    kashiFactionInMasterChef(kashiPairInfo.pid)
                );
            }

            kashiPairs[i].kashiPair.transfer(
                _newStrategy,
                kashiFractionInPair(kashiPairInfo.kashiPair)
            );
        }
    }

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

    function removeKashiPair(
        address _remKashiPair,
        uint256 _remIndex,
        bool _force
    ) external onlyEmergencyAuthorized {
        KashiPairInfo memory kashiPairInfo = kashiPairs[_remIndex];

        require(_remKashiPair == address(kashiPairInfo.kashiPair));

        liquidateKashiPair(
            kashiPairInfo.kashiPair,
            kashiPairInfo.pid,
            type(uint256).max // liquidateAll
        );

        if (!_force) {
            // must have liquidated all but dust
            require(
                kashiFractionTotal(
                    kashiPairInfo.kashiPair,
                    kashiPairInfo.pid
                ) <= dustThreshold
            );
        }

        if (kashiPairInfo.pid != 0) {
            IERC20(_remKashiPair).safeApprove(address(masterChef), 0);
        }
        kashiPairs[_remIndex] = kashiPairs[kashiPairs.length - 1];
        kashiPairs.pop();
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
            accrueInterest(kashiPairs[i].kashiPair);
            totalRatio += _ratios[i];
        }

        require(totalRatio == MAX_BPS); //ratios must add to 10000 bps

        uint256 wantBalance = balanceOfWant();
        if (wantBalance > dustThreshold) {
            depositInBento(wantBalance);
        }

        uint256 totalAssets = estimatedTotalAssets();
        uint256[] memory kashiPairsIncreasedAllocation =
            new uint256[](kashiPairs.length);

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            KashiPairInfo memory kashiPairInfo = kashiPairs[i];

            uint256 pairTotalAssets =
                bentoSharesToWant(
                    kashiFractionToBentoShares(
                        kashiPairInfo.kashiPair,
                        kashiFractionTotal(
                            kashiPairInfo.kashiPair,
                            kashiPairInfo.pid
                        )
                    )
                );
            uint256 targetAssets = (_ratios[i] * totalAssets) / MAX_BPS;
            if (targetAssets < pairTotalAssets) {
                uint256 toLiquidate = pairTotalAssets.sub(targetAssets);
                liquidateKashiPair(
                    kashiPairInfo.kashiPair,
                    kashiPairInfo.pid,
                    wantToBentoShares(toLiquidate)
                );
            } else if (targetAssets > pairTotalAssets) {
                kashiPairsIncreasedAllocation[i] = targetAssets.sub(
                    pairTotalAssets
                );
            }
        }

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            if (kashiPairsIncreasedAllocation[i] == 0) continue;

            KashiPairInfo memory kashiPairInfo = kashiPairs[i];

            uint256 sharesInBento = sharesInBento();
            uint256 sharesToAdd =
                wantToBentoShares(kashiPairsIncreasedAllocation[i]);

            if (sharesToAdd > sharesInBento) {
                sharesToAdd = sharesInBento;
            }

            depositInKashiPair(
                kashiPairInfo.kashiPair,
                kashiPairInfo.pid,
                sharesToAdd
            );
        }
    }

    function depositInKashiPair(
        IKashiPair kashiPair,
        uint256 pid,
        uint256 sharesToDeposit
    ) internal {
        transferBento(address(kashiPair), sharesToDeposit);

        uint256 depositedFraction =
            kashiPair.addAsset(address(this), true, sharesToDeposit);

        depositKashiInMasterChef(kashiPair, pid);
    }

    function depositKashiInMasterChef(IKashiPair kashiPair, uint256 pid)
        internal
    {
        if (pid == 0) return;

        uint256 fractionsToStake = kashiFractionInPair(kashiPair);
        masterChef.deposit(pid, fractionsToStake);
    }

    function depositInBento(uint256 wantToDeposit)
        internal
        returns (uint256 amountOut, uint256 shareOut)
    {
        return
            bentoBox.deposit(
                BIERC20(address(want)),
                address(this),
                address(this),
                wantToDeposit,
                0
            );
    }

    function transferBento(address to, uint256 shares) internal {
        bentoBox.transfer(
            BIERC20(address(want)),
            address(this),
            address(to),
            shares
        );
    }

    function liquidateKashiPair(
        IKashiPair kashiPair,
        uint256 pid,
        uint256 sharesToFree
    ) internal returns (uint256 _shareLiquidated) {
        // We need to call accrue to accurately calculate totalAssets
        accrueInterest(kashiPair);

        uint256 liquidShares = kashiPairLiquidShares(kashiPair);
        if (sharesToFree > liquidShares) {
            sharesToFree = liquidShares;
        }

        if (sharesToFree == 0) return 0;

        uint256 fractionsToFree =
            bentoSharesToKashiFraction(kashiPair, sharesToFree);

        // Remove from masterChef if there is a non-zero pid
        if (pid != 0) {
            uint256 fractionInMc = kashiFactionInMasterChef(pid);
            uint256 fractionsToFreeFromMc = fractionsToFree;
            if (fractionsToFreeFromMc.add(dustThreshold) > fractionInMc) {
                fractionsToFreeFromMc = fractionInMc;
            }
            masterChef.withdraw(pid, fractionsToFreeFromMc);
        }

        uint256 fractionBalance = kashiFractionInPair(kashiPair);

        if (fractionsToFree.add(dustThreshold) > fractionBalance) {
            fractionsToFree = fractionBalance;
        }

        _shareLiquidated = kashiPair.removeAsset(
            address(this),
            fractionsToFree
        );

        // Redeposit into the masterChef if there's some spare change
        depositKashiInMasterChef(kashiPair, pid);
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

    function accrueInterest(IKashiPair kashiPair) internal {
        (, uint256 lastAccrued, ) = kashiPair.accrueInfo();
        // Accure interest
        if (block.timestamp > lastAccrued) {
            kashiPair.accrue();
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

    function balanceOfWant() internal view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function balanceOfSushi() internal view returns (uint256) {
        return sushi.balanceOf(address(this));
    }

    function sharesInBento() internal view returns (uint256) {
        return bentoBox.balanceOf(BIERC20(address(want)), address(this));
    }

    function kashiFractionTotal(IKashiPair kashiPair, uint256 pid)
        internal
        view
        returns (uint256)
    {
        return
            kashiFactionInMasterChef(pid).add(kashiFractionInPair(kashiPair));
    }

    function kashiFactionInMasterChef(uint256 pid)
        internal
        view
        returns (uint256 _kashiFraction)
    {
        if (pid != 0) {
            _kashiFraction = masterChef.userInfo(pid, address(this)).amount;
        }
    }

    function kashiFractionInPair(IKashiPair kashiPair)
        internal
        view
        returns (uint256)
    {
        return kashiPair.balanceOf(address(this));
    }

    function kashiPairLiquidShares(IKashiPair kashiPair)
        internal
        view
        returns (uint256)
    {
        return kashiPair.totalAsset().elastic;
    }

    // highestInterestIndex finds the best pair to invest the given deposit
    function highestInterestPair(uint256 sharesToDeposit)
        internal
        view
        returns (IKashiPair _highestPair, uint256 _highestPid)
    {
        uint256 highestInterest = 0;
        uint256 highestUtilization = 0;

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            KashiPairInfo memory kashiPairInfo = kashiPairs[i];

            (uint256 interestPerBlock, , ) =
                kashiPairInfo.kashiPair.accrueInfo();

            uint256 utilization =
                kashiPairUtilization(kashiPairInfo.kashiPair, sharesToDeposit);

            // A pair is highest (really best) if either
            //   - It's utilization is higher, and either
            //     - It is above the max target util
            //     - The existing choice is below the min util target
            //   - Compare APR directly only if both are between the min and max
            if (
                (utilization > highestUtilization &&
                    (utilization > KASHI_MAXIMUM_TARGET_UTILIZATION ||
                        highestUtilization <
                        KASHI_MINIMUM_TARGET_UTILIZATION)) ||
                (interestPerBlock > highestInterest &&
                    utilization < KASHI_MAXIMUM_TARGET_UTILIZATION &&
                    utilization > KASHI_MINIMUM_TARGET_UTILIZATION &&
                    highestUtilization < KASHI_MAXIMUM_TARGET_UTILIZATION &&
                    highestUtilization > KASHI_MINIMUM_TARGET_UTILIZATION)
            ) {
                highestInterest = interestPerBlock;
                highestUtilization = utilization;
                _highestPair = kashiPairInfo.kashiPair;
                _highestPid = kashiPairInfo.pid;
            }
        }
    }

    function lowestInterestPair(uint256 minLiquidShares)
        internal
        view
        returns (IKashiPair _lowestPair, uint256 _lowestPid)
    {
        uint256 lowestInterest = type(uint256).max;
        uint256 lowestUtilization = KASHI_UTILIZATION_PRECISION;

        for (uint256 i = 0; i < kashiPairs.length; i++) {
            KashiPairInfo memory kashiPairInfo = kashiPairs[i];

            (uint256 interestPerBlock, , ) =
                kashiPairInfo.kashiPair.accrueInfo();

            uint256 utilization =
                kashiPairUtilization(kashiPairInfo.kashiPair, 0);

            // A pair is lowest if either
            //   - It's utilization is lower, and either
            //     - It is below the min taget util
            //     - The existing choice is above the max target util
            //   - Compare APR directly only if both are between the min and max
            if (
                ((utilization < lowestUtilization &&
                    (lowestUtilization > KASHI_MAXIMUM_TARGET_UTILIZATION ||
                        utilization < KASHI_MINIMUM_TARGET_UTILIZATION)) ||
                    (interestPerBlock < lowestInterest &&
                        utilization < KASHI_MAXIMUM_TARGET_UTILIZATION &&
                        utilization > KASHI_MINIMUM_TARGET_UTILIZATION &&
                        lowestUtilization < KASHI_MAXIMUM_TARGET_UTILIZATION &&
                        lowestUtilization >
                        KASHI_MINIMUM_TARGET_UTILIZATION)) &&
                kashiFractionTotal(kashiPairInfo.kashiPair, kashiPairInfo.pid) >
                dustThreshold &&
                kashiPairLiquidShares(kashiPairInfo.kashiPair) >=
                minLiquidShares
            ) {
                lowestInterest = interestPerBlock;
                _lowestPair = kashiPairInfo.kashiPair;
                _lowestPid = kashiPairInfo.pid;
            }
        }
    }

    function kashiPairUtilization(IKashiPair kashiPair, uint256 sharesToDeposit)
        internal
        view
        returns (uint256)
    {
        uint256 totalAssetShares = kashiPair.totalAsset().elastic;
        uint256 totalBorrowAmount = kashiPair.totalBorrow().elastic;
        uint256 fullAssetAmount =
            bentoBox
                .toAmount(
                BIERC20(address(this)),
                totalAssetShares.add(sharesToDeposit),
                false
            )
                .add(totalBorrowAmount);

        return
            uint256(totalBorrowAmount).mul(KASHI_UTILIZATION_PRECISION).div(
                fullAssetAmount
            );
    }

    function wantToBentoShares(uint256 wantAmount)
        internal
        view
        returns (uint256)
    {
        if (wantAmount == 0) return 0;
        return bentoBox.toShare(BIERC20(address(this)), wantAmount, true);
    }

    function bentoSharesToWant(uint256 bentoShares)
        internal
        view
        returns (uint256)
    {
        if (bentoShares == 0) return 0;
        return bentoBox.toAmount(BIERC20(address(this)), bentoShares, true);
    }

    function bentoSharesToKashiFraction(
        IKashiPair kashiPair,
        uint256 bentoShares
    ) internal view returns (uint256 _kashiFraction) {
        // Adapted from https://github.com/sushiswap/kashi-lending/blob/b6e3521d8628a835935c94a9039cfd192044d66b/contracts/KashiPair.sol#L320-L323
        Rebase memory totalAsset = kashiPair.totalAsset();
        Rebase memory totalBorrow = kashiPair.totalBorrow();
        uint256 allShare =
            uint256(totalAsset.elastic).add(
                wantToBentoShares(totalBorrow.elastic)
            );
        _kashiFraction = allShare == 0
            ? bentoShares
            : bentoShares.mul(totalAsset.base).div(allShare);
    }

    function kashiFractionToBentoShares(
        IKashiPair kashiPair,
        uint256 _kashiFraction
    ) internal view returns (uint256 bentoShares) {
        // Adapted from https://github.com/sushiswap/kashi-lending/blob/b6e3521d8628a835935c94a9039cfd192044d66b/contracts/KashiPair.sol#L351-L353
        Rebase memory totalAsset = kashiPair.totalAsset();
        Rebase memory totalBorrow = kashiPair.totalBorrow();
        uint256 allShare =
            uint256(totalAsset.elastic).add(
                wantToBentoShares(totalBorrow.elastic)
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
