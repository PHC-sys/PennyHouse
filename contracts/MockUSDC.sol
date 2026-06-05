// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// 테스트 전용 — 실제 배포 X
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockUSDC is ERC20 {
    constructor() ERC20("Mock USDC", "USDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    // 누구든 원하는 만큼 발행 가능 (테스트 전용)
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
