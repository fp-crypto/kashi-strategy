// SPDX-License-Identifier: MIT
pragma solidity 0.6.12;
import "../../../boringcrypto/boring-solidity/interfaces/IERC20.sol";

interface IFlashBorrower {
    function onFlashLoan(
        address sender,
        BIERC20 token,
        uint256 amount,
        uint256 fee,
        bytes calldata data
    ) external;
}
