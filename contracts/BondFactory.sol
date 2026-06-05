// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "./StructuredBond.sol";

contract BondFactory {

    // ── 허용된 USDC 주소 화이트리스트 ───────────────────────
    address public owner;
    mapping(address => bool) public allowedUSDC;

    // ── 채권 목록 ────────────────────────────────────────────
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
    event USDCAllowed(address indexed token, bool allowed);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    // ── USDC 화이트리스트 관리 (플랫폼 운영자만) ────────────
    function setAllowedUSDC(address token, bool allowed) external onlyOwner {
        require(token != address(0), "invalid token");
        allowedUSDC[token] = allowed;
        emit USDCAllowed(token, allowed);
    }

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
        require(allowedUSDC[usdc],        "usdc not whitelisted");

        StructuredBond bond = new StructuredBond(
            name,
            symbol,
            msg.sender,
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
