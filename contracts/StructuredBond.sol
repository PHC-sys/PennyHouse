// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title  StructuredBond
 * @notice ERC-20 기반 구조화채권.
 *         - 청약(Subscribe) → 발효(Issue) → 지급(Claim) → 소각(Redeem)
 *         - 무이표채: paymentSchedule 길이 1 (isPrincipal = true)
 *         - 이표채:   paymentSchedule 길이 N (마지막만 isPrincipal = true)
 *         - Act/360 이자 계산 (달러 기준)
 */
contract StructuredBond is ERC20, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ── 발행자 / 기본 설정 ──────────────────────────────────
    address public  issuer;
    IERC20  public  immutable usdc;
    address public  immutable opsWallet;

    // ── 채권 조건 ────────────────────────────────────────────
    uint256 public immutable maxNotional;       // 최대 모집액 (USDC, 6 decimals)
    uint256 public immutable couponRateBps;     // 연 이율 (bps, 1000 = 10%)
    uint256 public immutable subscriptionStart; // 청약 시작일 (unix timestamp)
    uint256 public immutable issueDate;         // 발효일: 이자 기산, 자금 릴리즈
    uint256 public immutable reserveBufferDays; // 지급 N일 전에 Reserve 체크

    // ── 지급 스케줄 ─────────────────────────────────────────
    struct Payment {
        uint256 date;            // 지급일 (unix timestamp)
        uint256 amountPerToken;  // 토큰 1개당 USDC (6 decimals 기준)
        bool    isPrincipal;     // true = 원금 포함, 토큰 소각
    }
    Payment[] public paymentSchedule;

    // ── 청약 상태 ────────────────────────────────────────────
    uint256 public totalSubscribed;
    mapping(address => uint256) public subscriptions;
    bool    public issuanceComplete;

    // ── Reserve 상태 ─────────────────────────────────────────
    uint256 public reserveBalance;
    bool    public opsWalletRevealed;

    // ── 지급 추적 ────────────────────────────────────────────
    // 이중 지급 방지: 회차별 총 지급 상한 + 누적 + 주소별 청구 여부
    mapping(uint256 => uint256) public paymentCap;
    mapping(uint256 => uint256) public cumulativeClaimed;
    mapping(address => mapping(uint256 => bool)) public claimed;

    // ── 이벤트 ──────────────────────────────────────────────
    event Subscribed(address indexed investor, uint256 amount);
    event SubscriptionCancelled(address indexed investor, uint256 amount);
    event IssuanceCompleted(uint256 issuedNotional);
    event Reserved(uint256 amount, uint256 total);
    event PaymentClaimed(address indexed holder, uint256 paymentIndex, uint256 amount);
    event OpsWalletRevealed(address opsWallet);
    event IssuerTransferred(address indexed oldIssuer, address indexed newIssuer);
    event ReserveWithdrawn(uint256 amount);

    constructor(
        string   memory _name,
        string   memory _symbol,
        address  _issuer,
        address  _usdc,
        address  _opsWallet,
        uint256  _maxNotional,
        uint256  _couponRateBps,
        uint256  _subscriptionStart,
        uint256  _issueDate,
        uint256  _reserveBufferDays,
        uint256[] memory _paymentDates,
        uint256[] memory _amountsPerToken,
        bool[]    memory _isPrincipal
    ) ERC20(_name, _symbol) {
        // 기본 검증
        require(_issuer    != address(0), "invalid issuer");
        require(_usdc      != address(0), "invalid usdc");
        require(_opsWallet != address(0), "invalid opsWallet");
        require(_maxNotional   > 0,       "notional must be > 0");
        require(_couponRateBps > 0,       "rate must be > 0");
        require(_subscriptionStart < _issueDate, "issue date must be after sub start");

        // 스케줄 검증
        uint256 len = _paymentDates.length;
        require(len > 0, "need at least one payment");
        require(
            len == _amountsPerToken.length && len == _isPrincipal.length,
            "array length mismatch"
        );
        require(_paymentDates[0] > _issueDate,  "first payment must be after issue date");
        require(_isPrincipal[len - 1],           "last payment must include principal");

        for (uint256 i = 0; i < len; i++) {
            if (i > 0) require(_paymentDates[i] > _paymentDates[i - 1], "dates must be ascending");
            require(_amountsPerToken[i] > 0, "amount must be > 0");
        }

        issuer            = _issuer;
        usdc              = IERC20(_usdc);
        opsWallet         = _opsWallet;
        maxNotional       = _maxNotional;
        couponRateBps     = _couponRateBps;
        subscriptionStart = _subscriptionStart;
        issueDate         = _issueDate;
        reserveBufferDays = _reserveBufferDays;

        for (uint256 i = 0; i < len; i++) {
            paymentSchedule.push(Payment({
                date:           _paymentDates[i],
                amountPerToken: _amountsPerToken[i],
                isPrincipal:    _isPrincipal[i]
            }));
        }
    }

    // ── 1. 청약 ─────────────────────────────────────────────
    function subscribe(uint256 amount) external nonReentrant {
        require(block.timestamp >= subscriptionStart, "subscription not started");
        require(block.timestamp <  issueDate,         "subscription closed");
        require(!issuanceComplete,                    "already issued");
        require(amount > 0,                           "amount must be > 0");

        uint256 remaining = maxNotional - totalSubscribed;
        require(remaining > 0, "fully subscribed");

        // FCFS: 남은 한도 내에서만 수락
        uint256 actual = amount > remaining ? remaining : amount;

        usdc.safeTransferFrom(msg.sender, address(this), actual);
        _mint(msg.sender, actual); // 1:1 PAR 발행

        subscriptions[msg.sender] += actual;
        totalSubscribed           += actual;

        emit Subscribed(msg.sender, actual);
    }

    // ── 2. 청약 취소 (발효일 전) ────────────────────────────
    function cancelSubscription() external nonReentrant {
        require(block.timestamp < issueDate, "subscription period ended");
        require(!issuanceComplete,           "already issued");

        uint256 amount = subscriptions[msg.sender];
        require(amount > 0, "no subscription");

        subscriptions[msg.sender] = 0;
        totalSubscribed           -= amount;

        _burn(msg.sender, amount);
        usdc.safeTransfer(msg.sender, amount);

        emit SubscriptionCancelled(msg.sender, amount);
    }

    // ── 3. 발행 완료 (누구나 호출) ──────────────────────────────
    // 조건: 발효일 경과 OR 완판(totalSubscribed >= maxNotional)
    // USDC 에스크로 → 발행자 지갑으로 릴리즈
    function completeIssuance() external nonReentrant {
        require(
            block.timestamp >= issueDate || totalSubscribed >= maxNotional,
            "not ready: wait for issue date or full subscription"
        );
        require(!issuanceComplete, "already complete");

        issuanceComplete = true;
        if (totalSubscribed > 0) {
            usdc.safeTransfer(issuer, totalSubscribed);
        }

        emit IssuanceCompleted(totalSubscribed);
    }

    // ── 4. Reserve 적립 (발행자만) ──────────────────────────
    function reserve(uint256 amount) external nonReentrant {
        require(msg.sender == issuer, "only issuer");
        require(amount > 0,           "amount must be > 0");

        usdc.safeTransferFrom(msg.sender, address(this), amount);
        reserveBalance += amount;

        emit Reserved(amount, reserveBalance);
    }

    // ── 5. Reserve 체크포인트 (지급 N일 전, 누구나 호출) ────
    function checkReserveForPayment(uint256 paymentIndex) external {
        require(paymentIndex < paymentSchedule.length, "invalid index");

        Payment memory p  = paymentSchedule[paymentIndex];
        uint256 checkDate = p.date - (reserveBufferDays * 1 days);
        require(block.timestamp >= checkDate, "too early for reserve check");

        uint256 required = totalSupply() * p.amountPerToken / 1e6;
        if (reserveBalance < required && !opsWalletRevealed) {
            opsWalletRevealed = true;
            emit OpsWalletRevealed(opsWallet);
        }
    }

    // ── 6. 지급 청구 ────────────────────────────────────────
    // 쿠폰: 토큰 유지  |  원금(isPrincipal): 토큰 소각
    // CEI 패턴 준수
    function claim(uint256 paymentIndex) external nonReentrant {
        require(issuanceComplete,                      "issuance not complete");
        require(paymentIndex < paymentSchedule.length, "invalid index");

        Payment memory p = paymentSchedule[paymentIndex];
        require(block.timestamp >= p.date,          "payment not yet due");
        require(!claimed[msg.sender][paymentIndex], "already claimed");

        uint256 tokenBalance = balanceOf(msg.sender);
        require(tokenBalance > 0, "no tokens");

        // 최초 청구 시 이 회차의 총 지급 상한 확정
        if (paymentCap[paymentIndex] == 0) {
            paymentCap[paymentIndex] = totalSupply() * p.amountPerToken / 1e6;
        }

        uint256 payment = tokenBalance * p.amountPerToken / 1e6;
        require(
            cumulativeClaimed[paymentIndex] + payment <= paymentCap[paymentIndex],
            "payment cap exceeded"
        );
        require(reserveBalance >= payment, "insufficient reserve");

        // Effects
        claimed[msg.sender][paymentIndex] = true;
        cumulativeClaimed[paymentIndex]  += payment;
        reserveBalance                   -= payment;
        if (p.isPrincipal) {
            _burn(msg.sender, tokenBalance);
        }

        // Interactions
        usdc.safeTransfer(msg.sender, payment);

        emit PaymentClaimed(msg.sender, paymentIndex, payment);
    }

    // ── 7. 일괄 지급 청구 (도래한 모든 회차) ────────────────
    // 미수령 쿠폰 + 원금을 한 번의 트랜잭션으로 수령 (가스비 절약)
    function claimAll() external nonReentrant {
        require(issuanceComplete, "issuance not complete");
        uint256 tokenBalance = balanceOf(msg.sender);
        require(tokenBalance > 0, "no tokens");

        for (uint256 i = 0; i < paymentSchedule.length; i++) {
            Payment memory p = paymentSchedule[i];
            if (block.timestamp < p.date) break;   // 아직 미도래 → 이후도 불필요
            if (claimed[msg.sender][i]) continue;  // 이미 수령 → 건너뜀

            if (paymentCap[i] == 0) {
                paymentCap[i] = totalSupply() * p.amountPerToken / 1e6;
            }

            uint256 payment = tokenBalance * p.amountPerToken / 1e6;
            require(cumulativeClaimed[i] + payment <= paymentCap[i], "payment cap exceeded");
            require(reserveBalance >= payment, "insufficient reserve");

            // Effects
            claimed[msg.sender][i]  = true;
            cumulativeClaimed[i]   += payment;
            reserveBalance         -= payment;

            // Interactions
            usdc.safeTransfer(msg.sender, payment);
            emit PaymentClaimed(msg.sender, i, payment);

            if (p.isPrincipal) {
                _burn(msg.sender, tokenBalance);
                break; // 토큰 소각 후 더 이상 진행 불가
            }
        }
    }

    // ── 9. 잉여 Reserve 회수 (발행자만) ─────────────────────
    function withdrawExcessReserve() external nonReentrant {
        require(msg.sender == issuer, "only issuer");

        // 다음 미도래 지급 회차의 최소 Reserve 계산
        uint256 required = 0;
        for (uint256 i = 0; i < paymentSchedule.length; i++) {
            if (block.timestamp < paymentSchedule[i].date) {
                required = totalSupply() * paymentSchedule[i].amountPerToken / 1e6;
                break;
            }
        }

        uint256 excess = reserveBalance > required ? reserveBalance - required : 0;
        require(excess > 0, "no excess reserve");

        reserveBalance -= excess;
        usdc.safeTransfer(issuer, excess);

        emit ReserveWithdrawn(excess);
    }

    // ── 10. 발행자 주소 이전 ────────────────────────────────
    function transferIssuer(address newIssuer) external {
        require(msg.sender == issuer,    "only issuer");
        require(newIssuer != address(0), "invalid address");
        emit IssuerTransferred(issuer, newIssuer);
        issuer = newIssuer;
    }

    // ── 조회 함수 ────────────────────────────────────────────

    // 전체 지급 스케줄 반환
    function getPaymentSchedule() external view returns (Payment[] memory) {
        return paymentSchedule;
    }

    // 경과이자 (Act/360, 직전 지급일 기준, 토큰 1개당 USDC)
    // 프론트엔드에서 Dirty Price 표시에 사용
    function accruedInterestPerToken() external view returns (uint256) {
        if (!issuanceComplete || totalSupply() == 0) return 0;

        // 직전 지급일 탐색
        uint256 lastDate = issueDate;
        for (uint256 i = 0; i < paymentSchedule.length; i++) {
            if (block.timestamp >= paymentSchedule[i].date) {
                lastDate = paymentSchedule[i].date;
            } else {
                break;
            }
        }

        uint256 elapsed = block.timestamp > lastDate ? block.timestamp - lastDate : 0;
        // Act/360: 1 USDC(1e6) × rate(bps) × elapsed(초) / (360일(초) × 10000)
        return (1e6 * couponRateBps * elapsed) / (360 days * 10000);
    }

    // 특정 지급 회차의 Reserve 현황
    function getReserveStatus(uint256 paymentIndex) external view returns (
        uint256 balance,
        uint256 required,
        bool    sufficient
    ) {
        if (paymentIndex >= paymentSchedule.length) return (reserveBalance, 0, true);
        uint256 req = totalSupply() * paymentSchedule[paymentIndex].amountPerToken / 1e6;
        return (reserveBalance, req, reserveBalance >= req);
    }

    // 운용 지갑: Reserve 부족 시에만 공개
    function getOpsWallet() external view returns (address) {
        return opsWalletRevealed ? opsWallet : address(0);
    }

    function paymentCount() external view returns (uint256) {
        return paymentSchedule.length;
    }

    function decimals() public pure override returns (uint8) { return 6; }
}
