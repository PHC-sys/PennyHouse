// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract StructuredBond is ERC20 {

    // ── 발행자 ──────────────────────────────────────────────
    address public issuer;
    IERC20  public usdc;

    // ── 채권 조건 ────────────────────────────────────────────
    uint256 public notional;         // 총 원금 (USDC, 6 decimals)
    uint256 public couponRateBps;    // 연 이율 (basis points, 1000 = 10%)
    uint256 public issuanceDate;     // 발행일 (unix timestamp)
    uint256 public maturityDate;     // 만기일 (unix timestamp)
    uint256 public paymentPerToken;  // 토큰 1개당 만기 지급액 (USDC, 6 decimals)

    // ── 상태 ─────────────────────────────────────────────────
    bool    public settled;          // 정산 완료 여부
    uint256 public reserveBalance;   // 컨트랙트 내 적립 USDC

    // ── Reserve 투명성 ───────────────────────────────────────
    address public opsWallet;
    bool    public opsWalletRevealed;

    // ── 이벤트 ───────────────────────────────────────────────
    event BondIssued(uint256 totalSupply, uint256 maturityDate, uint256 paymentPerToken);
    event Reserved(uint256 amount, uint256 total);
    event Redeemed(address indexed holder, uint256 tokenAmount, uint256 usdcAmount);
    event OpsWalletRevealed(address opsWallet);

    constructor(
        string  memory _name,
        string  memory _symbol,
        address _usdc,
        address _opsWallet,
        uint256 _notional,       // e.g. 10000000000 (10,000 USDC, 6 decimals)
        uint256 _couponRateBps,  // e.g. 1000 (10%)
        uint256 _maturityDays    // e.g. 7
    ) ERC20(_name, _symbol) {
        require(_notional > 0,      "notional must be > 0");
        require(_couponRateBps > 0, "rate must be > 0");
        require(_maturityDays > 0,  "maturity must be > 0");
        require(_opsWallet != address(0), "invalid opsWallet");

        issuer        = msg.sender;
        usdc          = IERC20(_usdc);
        opsWallet     = _opsWallet;
        notional      = _notional;
        couponRateBps = _couponRateBps;
        issuanceDate  = block.timestamp;
        maturityDate  = block.timestamp + (_maturityDays * 1 days);

        // 토큰 1개당 이자 = 1 USDC × rate × (days / 360)  [30/360 단순화]
        uint256 interestPerToken = (1e6 * _couponRateBps * _maturityDays) / (360 * 10000);
        paymentPerToken = 1e6 + interestPerToken;

        // 토큰 총 발행 (발행자에게), 1토큰 = 1 USDC 액면
        _mint(msg.sender, _notional);

        emit BondIssued(_notional, maturityDate, paymentPerToken);
    }

    // ── 1. Reserve 적립 (발행자만) ──────────────────────────
    function reserve(uint256 amount) external {
        require(msg.sender == issuer, "only issuer");
        require(!settled, "already settled");
        usdc.transferFrom(msg.sender, address(this), amount);
        reserveBalance += amount;
        emit Reserved(amount, reserveBalance);
        _checkReserve();
    }

    // ── 2. 만기 상환 (토큰 보유자) ──────────────────────────
    function redeem() external {
        require(block.timestamp >= maturityDate, "not matured yet");
        require(!settled, "already settled");

        uint256 tokenBalance = balanceOf(msg.sender);
        require(tokenBalance > 0, "no tokens to redeem");

        uint256 payment = (tokenBalance * paymentPerToken) / 1e6;
        require(reserveBalance >= payment, "insufficient reserve");

        _burn(msg.sender, tokenBalance);
        reserveBalance -= payment;
        usdc.transfer(msg.sender, payment);

        if (totalSupply() == 0) settled = true;

        emit Redeemed(msg.sender, tokenBalance, payment);
    }

    // ── 3. Reserve 부족 체크 ─────────────────────────────────
    function _checkReserve() internal {
        uint256 required = (totalSupply() * paymentPerToken) / 1e6;
        if (reserveBalance < required && !opsWalletRevealed) {
            opsWalletRevealed = true;
            emit OpsWalletRevealed(opsWallet);
        }
    }

    function checkReserve() external {
        _checkReserve();
    }

    // ── 4. 조회 함수 ─────────────────────────────────────────
    function getBondTerms() external view returns (
        uint256 _notional,
        uint256 _couponRateBps,
        uint256 _issuanceDate,
        uint256 _maturityDate,
        uint256 _paymentPerToken,
        uint256 _secondsToMaturity
    ) {
        uint256 timeLeft = block.timestamp < maturityDate
            ? maturityDate - block.timestamp : 0;
        return (notional, couponRateBps, issuanceDate, maturityDate, paymentPerToken, timeLeft);
    }

    function getReserveStatus() external view returns (
        uint256 _balance,
        uint256 _required,
        bool    _sufficient,
        bool    _opsRevealed,
        address _opsWallet
    ) {
        uint256 required = (totalSupply() * paymentPerToken) / 1e6;
        return (
            reserveBalance,
            required,
            reserveBalance >= required,
            opsWalletRevealed,
            opsWalletRevealed ? opsWallet : address(0)
        );
    }

    function isMatured() external view returns (bool) {
        return block.timestamp >= maturityDate;
    }

    // USDC는 6 decimals
    function decimals() public pure override returns (uint8) {
        return 6;
    }
}
