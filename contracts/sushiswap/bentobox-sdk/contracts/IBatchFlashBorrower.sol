// SPDX-License-Identifier: MIT
pragma solidity 0.6.12;
import "../../../boringcrypto/boring-solidity/interfaces/IERC20.sol";

interface IBatchFlashBorrower {
    function onBatchFlashLoan(
        address sender,
        BIERC20[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata fees,
        bytes calldata data
    ) external;
}
