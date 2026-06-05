// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract StructuredBond is ERC20, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ── 발행자 ──────────────────────────────────────────────
    address public issuer;           // 이전 가능 (키 탈취 대응)
    IERC20  public immutable usdc;

    // ── 채권 조건 ────────────────────────────────────────────
    uint256 public immutable notional;
    uint256 public immutable couponRateBps;
    uint256 public immutable issuanceDate;
    uint256 public immutable maturityDate;
    uint256 public immutable paymentPerToken;

    // ── 상태 ─────────────────────────────────────────────────
    uint256 public reserveBalance;

    // ── Reserve 투명성 ───────────────────────────────────────
    address public immutable opsWallet;
    bool    public opsWalletRevealed;

    // ── 이벤트 ───────────────────────────────────────────────
    event BondIssued(uint256 totalSupply, uint256 maturityDate, uint256 paymentPerToken);
    event Reserved(uint256 amount, uint256 total);
    event Redeemed(address indexed holder, uint256 tokenAmount, uint256 usdcAmount);
    event OpsWalletRevealed(address opsWallet);
    event IssuerTransferred(address indexed oldIssuer, address indexed newIssuer);
    event ReserveWithdrawn(address indexed issuer, uint256 amount);

    constructor(
        string  memory _name,
        string  memory _symbol,
        address _issuer,
        address _usdc,
        address _opsWallet,
        uint256 _notional,
        uint256 _couponRateBps,
        uint256 _maturityTimestamp
    ) ERC20(_name, _symbol) {
        require(_issuer != address(0),                "invalid issuer");
        require(_usdc != address(0),                  "invalid usdc address");
        require(_opsWallet != address(0),             "invalid opsWallet");
        require(_notional > 0,                        "notional must be > 0");
        require(_couponRateBps > 0,                   "rate must be > 0");
        require(_maturityTimestamp > block.timestamp, "maturity must be in the future");

        issuer        = _issuer;
        usdc          = IERC20(_usdc);
        opsWallet     = _opsWallet;
        notional      = _notional;
        couponRateBps = _couponRateBps;
        issuanceDate  = block.timestamp;
        maturityDate  = _maturityTimestamp;

        uint256 secondsToMaturity = _maturityTimestamp - block.timestamp;
        uint256 interestPerToken  = (1e6 * _couponRateBps * secondsToMaturity)
                                    / (360 days * 10000);
        paymentPerToken = 1e6 + interestPerToken;

        _mint(_issuer, _notional);

        emit BondIssued(_notional, maturityDate, paymentPerToken);
    }

    // ── 1. Reserve 적립 (발행자만) ──────────────────────────
    function reserve(uint256 amount) external nonReentrant {
        require(msg.sender == issuer, "only issuer");
        require(amount > 0,           "amount must be > 0");

        usdc.safeTransferFrom(msg.sender, address(this), amount);
        reserveBalance += amount;

        emit Reserved(amount, reserveBalance);
        _checkReserve();
    }

    // ── 2. 만기 상환 (토큰 보유자) ──────────────────────────
    function redeem() external nonReentrant {
        // Checks
        require(block.timestamp >= maturityDate, "not matured yet");

        uint256 tokenBalance = balanceOf(msg.sender);
        require(tokenBalance > 0, "no tokens to redeem");

        uint256 payment = (tokenBalance * paymentPerToken) / 1e6;
        require(reserveBalance >= payment, "insufficient reserve");

        // Effects
        _burn(msg.sender, tokenBalance);
        reserveBalance -= payment;

        // Interactions
        usdc.safeTransfer(msg.sender, payment);

        emit Redeemed(msg.sender, tokenBalance, payment);
    }

    // ── 3. 잉여 Reserve 회수 (발행자만, 만기 후) ────────────
    // 모든 투자자가 redeem 후 남은 USDC를 발행자가 회수
    function withdrawExcessReserve() external nonReentrant {
        require(msg.sender == issuer,            "only issuer");
        require(block.timestamp >= maturityDate, "not matured yet");

        // 남아있는 토큰 보유자에게 지급해야 할 최소 Reserve
        uint256 required = (totalSupply() * paymentPerToken) / 1e6;
        uint256 excess   = reserveBalance > required
                           ? reserveBalance - required : 0;

        require(excess > 0, "no excess reserve");

        reserveBalance -= excess;
        usdc.safeTransfer(issuer, excess);

        emit ReserveWithdrawn(issuer, excess);
    }

    // ── 4. 발행자 주소 이전 (키 탈취 대응) ─────────────────
    function transferIssuer(address newIssuer) external {
        require(msg.sender == issuer,      "only issuer");
        require(newIssuer != address(0),   "invalid address");
        emit IssuerTransferred(issuer, newIssuer);
        issuer = newIssuer;
    }

    // ── 5. Reserve 부족 체크 ─────────────────────────────────
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

    // ── 6. 조회 함수 ─────────────────────────────────────────
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

    function decimals() public pure override returns (uint8) {
        return 6;
    }
}
