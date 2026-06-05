// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./StructuredBond.sol";

contract BondFactory {

    // ── 상태 ─────────────────────────────────────────────────
    address[] public allBonds;
    mapping(address => address[]) public bondsByIssuer;

    // ── 이벤트 ───────────────────────────────────────────────
    event BondCreated(
        address indexed issuer,
        address indexed bondAddress,
        string  name,
        string  symbol,
        uint256 notional,
        uint256 couponRateBps,
        uint256 maturityDays
    );

    // ── 채권 발행 (누구나 호출 가능) ────────────────────────
    function createBond(
        string  memory name,
        string  memory symbol,
        address usdc,
        address opsWallet,
        uint256 notional,
        uint256 couponRateBps,
        uint256 maturityDays
    ) external returns (address) {
        require(bytes(name).length > 0,   "name required");
        require(bytes(symbol).length > 0, "symbol required");
        require(usdc != address(0),       "invalid usdc address");

        StructuredBond bond = new StructuredBond(
            name,
            symbol,
            usdc,
            opsWallet,
            notional,
            couponRateBps,
            maturityDays
        );

        // 발행된 토큰을 호출자(발행자)에게 전달
        // (StructuredBond가 Factory를 msg.sender로 인식하므로 토큰이 Factory에 발행됨)
        // → 발행자가 직접 배포하도록 issuer를 tx.origin으로 처리하거나
        //   Factory에서 토큰을 전달하는 방식 사용
        IERC20(address(bond)).transfer(msg.sender, IERC20(address(bond)).balanceOf(address(this)));

        allBonds.push(address(bond));
        bondsByIssuer[msg.sender].push(address(bond));

        emit BondCreated(
            msg.sender,
            address(bond),
            name,
            symbol,
            notional,
            couponRateBps,
            maturityDays
        );

        return address(bond);
    }

    // ── 조회 함수 ────────────────────────────────────────────
    function getAllBonds() external view returns (address[] memory) {
        return allBonds;
    }

    function getBondsByIssuer(address issuer) external view returns (address[] memory) {
        return bondsByIssuer[issuer];
    }

    function totalBonds() external view returns (uint256) {
        return allBonds.length;
    }
}
