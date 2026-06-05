// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

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
        uint256 maturityTimestamp
    );

    // ── 채권 발행 (누구나 호출 가능) ────────────────────────
    function createBond(
        string  memory name,
        string  memory symbol,
        address usdc,
        address opsWallet,
        uint256 notional,
        uint256 couponRateBps,
        uint256 maturityTimestamp
    ) external returns (address) {
        require(bytes(name).length > 0,   "name required");
        require(bytes(symbol).length > 0, "symbol required");
        require(usdc != address(0),       "invalid usdc address");

        // msg.sender(실제 발행자)를 _issuer로 넘김
        // → StructuredBond 내부 issuer = 사용자 지갑
        // → 토큰도 사용자 지갑으로 바로 발행
        StructuredBond bond = new StructuredBond(
            name,
            symbol,
            msg.sender,     // ← 실제 발행자
            usdc,
            opsWallet,
            notional,
            couponRateBps,
            maturityTimestamp
        );

        allBonds.push(address(bond));
        bondsByIssuer[msg.sender].push(address(bond));

        emit BondCreated(
            msg.sender,
            address(bond),
            name,
            symbol,
            notional,
            couponRateBps,
            maturityTimestamp
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
