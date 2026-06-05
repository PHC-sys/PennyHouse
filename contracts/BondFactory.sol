// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "./StructuredBond.sol";

contract BondFactory {

    // ── 운영자 / USDC 화이트리스트 ──────────────────────────
    address public owner;
    mapping(address => bool) public allowedUSDC;

    // ── 채권 목록 ────────────────────────────────────────────
    address[] public allBonds;
    mapping(address => address[]) public bondsByIssuer;

    // ── 파라미터 구조체 (stack too deep 방지) ────────────────
    struct BondParams {
        string   name;
        string   symbol;
        address  opsWallet;
        uint256  maxNotional;
        uint256  couponRateBps;
        uint256  subscriptionStart;
        uint256  issueDate;
        uint256  reserveBufferDays;
        uint256[] paymentDates;
        uint256[] amountsPerToken;
        bool[]    isPrincipal;
    }

    // ── 이벤트 ──────────────────────────────────────────────
    event BondCreated(
        address indexed issuer,
        address indexed bondAddress,
        string  name,
        string  symbol,
        uint256 maxNotional
    );
    event USDCAllowed(address indexed token, bool allowed);

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    // ── USDC 화이트리스트 (운영자만) ────────────────────────
    function setAllowedUSDC(address token, bool allowed) external onlyOwner {
        require(token != address(0), "invalid token");
        allowedUSDC[token] = allowed;
        emit USDCAllowed(token, allowed);
    }

    // ── 채권 발행 (누구나) ───────────────────────────────────
    function createBond(
        address usdc,
        BondParams calldata p
    ) external returns (address) {
        require(allowedUSDC[usdc],          "usdc not whitelisted");
        require(bytes(p.name).length > 0,   "name required");
        require(bytes(p.symbol).length > 0, "symbol required");

        StructuredBond bond = new StructuredBond(
            p.name,
            p.symbol,
            msg.sender,   // issuer = 호출자
            usdc,
            p.opsWallet,
            p.maxNotional,
            p.couponRateBps,
            p.subscriptionStart,
            p.issueDate,
            p.reserveBufferDays,
            p.paymentDates,
            p.amountsPerToken,
            p.isPrincipal
        );

        allBonds.push(address(bond));
        bondsByIssuer[msg.sender].push(address(bond));

        emit BondCreated(
            msg.sender,
            address(bond),
            p.name,
            p.symbol,
            p.maxNotional
        );

        return address(bond);
    }

    // ── 조회 ─────────────────────────────────────────────────
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
