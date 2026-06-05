// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract StructuredBond is ERC20, ReentrancyGuard {

    // ── 발행자 ──────────────────────────────────────────────
    address public immutable issuer;
    IERC20  public immutable usdc;

    // ── 채권 조건 ────────────────────────────────────────────
    uint256 public immutable notional;        // 총 원금 (USDC, 6 decimals)
    uint256 public immutable couponRateBps;   // 연 이율 (basis points, 1000 = 10%)
    uint256 public immutable issuanceDate;    // 발행일 (unix timestamp)
    uint256 public immutable maturityDate;    // 만기일 (unix timestamp) ← 날짜 직접 입력
    uint256 public immutable paymentPerToken; // 토큰 1개당 만기 지급액 (USDC, 6 decimals)

    // ── 상태 ─────────────────────────────────────────────────
    bool    public settled;
    uint256 public reserveBalance;

    // ── Reserve 투명성 ───────────────────────────────────────
    address public immutable opsWallet;
    bool    public opsWalletRevealed;

    // ── 이벤트 ───────────────────────────────────────────────
    event BondIssued(uint256 totalSupply, uint256 maturityDate, uint256 paymentPerToken);
    event Reserved(uint256 amount, uint256 total);
    event Redeemed(address indexed holder, uint256 tokenAmount, uint256 usdcAmount);
    event OpsWalletRevealed(address opsWallet);

    constructor(
        string  memory _name,
        string  memory _symbol,
        address _issuer,            // 실제 발행자 주소 (Factory 경유 시 tx 호출자)
        address _usdc,
        address _opsWallet,
        uint256 _notional,          // e.g. 10000000000 (10,000 USDC, 6 decimals)
        uint256 _couponRateBps,     // e.g. 1000 (10%)
        uint256 _maturityTimestamp  // 만기일 unix timestamp (프론트에서 날짜 → 변환)
    ) ERC20(_name, _symbol) {
        // ── 입력값 검증 ──────────────────────────────────────
        require(_issuer != address(0),                  "invalid issuer");
        require(_notional > 0,                          "notional must be > 0");
        require(_couponRateBps > 0,                     "rate must be > 0");
        require(_maturityTimestamp > block.timestamp,   "maturity must be in the future");
        require(_opsWallet != address(0),               "invalid opsWallet");
        require(_usdc != address(0),                    "invalid usdc address");

        issuer        = _issuer;    // Factory가 넘겨준 실제 발행자
        usdc          = IERC20(_usdc);
        opsWallet     = _opsWallet;
        notional      = _notional;
        couponRateBps = _couponRateBps;
        issuanceDate  = block.timestamp;
        maturityDate  = _maturityTimestamp;

        // 이자 계산: 초 단위로 정밀하게 (30/360 기준, 하루 = 86400초)
        // interest = notional × rate × (seconds / (360 days in seconds))
        uint256 secondsToMaturity = _maturityTimestamp - block.timestamp;
        uint256 interestPerToken  = (1e6 * _couponRateBps * secondsToMaturity)
                                    / (360 days * 10000);
        paymentPerToken = 1e6 + interestPerToken;

        // 토큰 전량 발행 → 실제 발행자에게
        _mint(_issuer, _notional);

        emit BondIssued(_notional, maturityDate, paymentPerToken);
    }

    // ── 1. Reserve 적립 (발행자만) ──────────────────────────
    function reserve(uint256 amount) external nonReentrant {
        require(msg.sender == issuer, "only issuer");
        require(!settled,             "already settled");
        require(amount > 0,           "amount must be > 0");

        usdc.transferFrom(msg.sender, address(this), amount);
        reserveBalance += amount;

        emit Reserved(amount, reserveBalance);
        _checkReserve();
    }

    // ── 2. 만기 상환 (토큰 보유자) ──────────────────────────
    // CEI 패턴 준수: Checks → Effects → Interactions
    function redeem() external nonReentrant {
        // Checks
        require(block.timestamp >= maturityDate, "not matured yet");
        require(!settled,                        "already settled");

        uint256 tokenBalance = balanceOf(msg.sender);
        require(tokenBalance > 0, "no tokens to redeem");

        uint256 payment = (tokenBalance * paymentPerToken) / 1e6;
        require(reserveBalance >= payment, "insufficient reserve");

        // Effects (상태 변경 먼저)
        _burn(msg.sender, tokenBalance);
        reserveBalance -= payment;

        // Interactions (외부 호출 마지막)
        usdc.transfer(msg.sender, payment);

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

    // USDC 6 decimals
    function decimals() public pure override returns (uint8) {
        return 6;
    }
}
