const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time }   = require("@nomicfoundation/hardhat-network-helpers");

// ─────────────────────────────────────────────────────────────
//  지급 금액 상수 (프론트에서 계산해서 넘기는 방식 시뮬레이션)
//  - COUPON_PER_TOKEN    : 5% 쿠폰 (0.05 USDC per 1 USDC face)
//  - PRINCIPAL_PER_TOKEN : 원금 1 USDC + 마지막 쿠폰 0.05 USDC
// ─────────────────────────────────────────────────────────────
const COUPON    = 50_000n;    // 0.05 USDC (6 decimals)
const PRINCIPAL = 1_050_000n; // 1.05 USDC (원금 + 쿠폰)
const NOTIONAL  = ethers.parseUnits("10000", 6); // 10,000 USDC

// ── 이표채 픽스처 ────────────────────────────────────────────
// paymentSchedule: [쿠폰(30일), 원금+쿠폰(60일)]
async function deployCouponBond() {
  const [owner, issuer, investor, investor2, opsWallet, other] =
    await ethers.getSigners();

  const now       = await time.latest();
  const subStart  = now;
  const issue     = now + 1  * 24 * 3600; // +1일
  const payment1  = now + 30 * 24 * 3600; // +30일 (쿠폰)
  const payment2  = now + 60 * 24 * 3600; // +60일 (원금+쿠폰)

  const MockUSDC = await ethers.getContractFactory("MockUSDC");
  const usdc = await MockUSDC.deploy();

  await usdc.mint(issuer.address,    ethers.parseUnits("1000000", 6));
  await usdc.mint(investor.address,  ethers.parseUnits("100000",  6));
  await usdc.mint(investor2.address, ethers.parseUnits("100000",  6));

  const Bond = await ethers.getContractFactory("StructuredBond");
  const bond = await Bond.deploy(
    "PENNY-BOND-001", "PB001",
    issuer.address,
    await usdc.getAddress(),
    opsWallet.address,
    NOTIONAL,
    1000,           // 연 10%
    subStart,
    issue,
    7,              // 7일 전 Reserve 체크
    [payment1, payment2],
    [COUPON, PRINCIPAL],
    [false, true]
  );

  return { bond, usdc, owner, issuer, investor, investor2,
           opsWallet, other, subStart, issue, payment1, payment2 };
}

// ── 무이표채 픽스처 ──────────────────────────────────────────
// paymentSchedule: [원금(60일, isPrincipal=true)]
async function deployZeroCouponBond() {
  const [, issuer, investor, , opsWallet] = await ethers.getSigners();

  const now      = await time.latest();
  const subStart = now;
  const issue    = now + 1  * 24 * 3600;
  const maturity = now + 60 * 24 * 3600;

  const MockUSDC = await ethers.getContractFactory("MockUSDC");
  const usdc = await MockUSDC.deploy();

  await usdc.mint(issuer.address,   ethers.parseUnits("1000000", 6));
  await usdc.mint(investor.address, ethers.parseUnits("100000",  6));

  const Bond = await ethers.getContractFactory("StructuredBond");
  const bond = await Bond.deploy(
    "ZERO-COUPON-001", "ZC001",
    issuer.address,
    await usdc.getAddress(),
    opsWallet.address,
    NOTIONAL,
    500,          // 연 5%
    subStart,
    issue,
    3,            // 3일 전 Reserve 체크
    [maturity],
    [PRINCIPAL],  // 원금+이자 일괄
    [true]
  );

  return { bond, usdc, issuer, investor, opsWallet, issue, maturity };
}

// ── 헬퍼: 청약 + 발행 완료 ──────────────────────────────────
async function subscribeAndIssue(bond, usdc, investor, amount, issueTs) {
  await usdc.connect(investor).approve(await bond.getAddress(), amount);
  await bond.connect(investor).subscribe(amount);
  await time.increaseTo(issueTs + 1);
  await bond.completeIssuance();
}

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 배포 검증", function () {

  it("채권 조건이 올바르게 저장된다", async function () {
    const { bond, issue } = await deployCouponBond();
    expect(await bond.maxNotional()).to.equal(NOTIONAL);
    expect(await bond.couponRateBps()).to.equal(1000);
    expect(await bond.issueDate()).to.equal(issue);
    expect(await bond.paymentCount()).to.equal(2);
  });

  it("첫 번째 지급일이 발효일보다 이전이면 배포 실패", async function () {
    const now = await time.latest();
    const [, issuer, , , opsWallet] = await ethers.getSigners();
    const MockUSDC = await ethers.getContractFactory("MockUSDC");
    const usdc = await MockUSDC.deploy();
    const Bond = await ethers.getContractFactory("StructuredBond");

    await expect(Bond.deploy(
      "BAD", "BAD", issuer.address, await usdc.getAddress(), opsWallet.address,
      NOTIONAL, 1000, now, now + 86400, 7,
      [now + 3600],   // ← 발효일보다 이전
      [PRINCIPAL], [true]
    )).to.be.revertedWith("first payment must be after issue date");
  });

  it("마지막 지급이 isPrincipal=false 면 배포 실패", async function () {
    const now = await time.latest();
    const [, issuer, , , opsWallet] = await ethers.getSigners();
    const MockUSDC = await ethers.getContractFactory("MockUSDC");
    const usdc = await MockUSDC.deploy();
    const Bond = await ethers.getContractFactory("StructuredBond");

    await expect(Bond.deploy(
      "BAD", "BAD", issuer.address, await usdc.getAddress(), opsWallet.address,
      NOTIONAL, 1000, now, now + 86400, 7,
      [now + 2 * 86400],
      [PRINCIPAL], [false]   // ← 마지막인데 isPrincipal=false
    )).to.be.revertedWith("last payment must include principal");
  });

  it("지급일이 오름차순이 아니면 배포 실패", async function () {
    const now = await time.latest();
    const [, issuer, , , opsWallet] = await ethers.getSigners();
    const MockUSDC = await ethers.getContractFactory("MockUSDC");
    const usdc = await MockUSDC.deploy();
    const Bond = await ethers.getContractFactory("StructuredBond");

    await expect(Bond.deploy(
      "BAD", "BAD", issuer.address, await usdc.getAddress(), opsWallet.address,
      NOTIONAL, 1000, now, now + 86400, 7,
      [now + 5 * 86400, now + 3 * 86400],  // ← 역순
      [COUPON, PRINCIPAL], [false, true]
    )).to.be.revertedWith("dates must be ascending");
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 청약(Subscribe)", function () {

  it("청약 기간에 정상 청약 가능", async function () {
    const { bond, usdc, investor } = await deployCouponBond();
    const amount = ethers.parseUnits("1000", 6);

    await usdc.connect(investor).approve(await bond.getAddress(), amount);
    await bond.connect(investor).subscribe(amount);

    expect(await bond.totalSubscribed()).to.equal(amount);
    expect(await bond.balanceOf(investor.address)).to.equal(amount);
    expect(await bond.subscriptions(investor.address)).to.equal(amount);
  });

  it("Notional 초과 청약 시 남은 한도만 수락 (FCFS)", async function () {
    const { bond, usdc, investor, investor2 } = await deployCouponBond();

    // investor: 9,000 청약
    const amt1 = ethers.parseUnits("9000", 6);
    await usdc.connect(investor).approve(await bond.getAddress(), amt1);
    await bond.connect(investor).subscribe(amt1);

    // investor2: 2,000 청약 시도 → 1,000만 수락
    const amt2 = ethers.parseUnits("2000", 6);
    const remaining = NOTIONAL - amt1;
    await usdc.connect(investor2).approve(await bond.getAddress(), amt2);
    await bond.connect(investor2).subscribe(amt2);

    expect(await bond.totalSubscribed()).to.equal(NOTIONAL);
    expect(await bond.balanceOf(investor2.address)).to.equal(remaining);
  });

  it("Notional 완판 후 추가 청약 불가", async function () {
    const { bond, usdc, investor, investor2 } = await deployCouponBond();

    await usdc.connect(investor).approve(await bond.getAddress(), NOTIONAL);
    await bond.connect(investor).subscribe(NOTIONAL);

    await usdc.connect(investor2).approve(await bond.getAddress(), ethers.parseUnits("1", 6));
    await expect(
      bond.connect(investor2).subscribe(ethers.parseUnits("1", 6))
    ).to.be.revertedWith("fully subscribed");
  });

  it("발효일 이후에는 청약 불가", async function () {
    const { bond, usdc, investor, issue } = await deployCouponBond();
    await time.increaseTo(issue + 1);

    await usdc.connect(investor).approve(await bond.getAddress(), ethers.parseUnits("1000", 6));
    await expect(
      bond.connect(investor).subscribe(ethers.parseUnits("1000", 6))
    ).to.be.revertedWith("subscription closed");
  });

  it("청약 취소 시 USDC 환불 + 토큰 소각", async function () {
    const { bond, usdc, investor } = await deployCouponBond();
    const amount = ethers.parseUnits("1000", 6);

    await usdc.connect(investor).approve(await bond.getAddress(), amount);
    await bond.connect(investor).subscribe(amount);

    const before = await usdc.balanceOf(investor.address);
    await bond.connect(investor).cancelSubscription();
    const after  = await usdc.balanceOf(investor.address);

    expect(after - before).to.equal(amount);
    expect(await bond.balanceOf(investor.address)).to.equal(0);
    expect(await bond.totalSubscribed()).to.equal(0);
  });

  it("발효일 이후에는 청약 취소 불가", async function () {
    const { bond, usdc, investor, issue } = await deployCouponBond();
    const amount = ethers.parseUnits("1000", 6);

    await usdc.connect(investor).approve(await bond.getAddress(), amount);
    await bond.connect(investor).subscribe(amount);
    await time.increaseTo(issue + 1);

    await expect(
      bond.connect(investor).cancelSubscription()
    ).to.be.revertedWith("subscription period ended");
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 발행 완료(completeIssuance)", function () {

  it("발효일 이후 누구나 발행 완료 호출 가능, USDC → 발행자", async function () {
    const { bond, usdc, issuer, investor, other, issue } = await deployCouponBond();
    const amount = ethers.parseUnits("5000", 6);

    await usdc.connect(investor).approve(await bond.getAddress(), amount);
    await bond.connect(investor).subscribe(amount);

    await time.increaseTo(issue + 1);

    const issuerBefore = await usdc.balanceOf(issuer.address);
    await bond.connect(other).completeIssuance(); // 누구나 호출 가능
    const issuerAfter  = await usdc.balanceOf(issuer.address);

    expect(issuerAfter - issuerBefore).to.equal(amount);
    expect(await bond.issuanceComplete()).to.equal(true);
  });

  it("미달 청약 시 들어온 만큼만 발행 (Notional 축소)", async function () {
    const { bond, usdc, investor, issue } = await deployCouponBond();
    const partial = ethers.parseUnits("3000", 6); // 10,000 중 3,000만

    await usdc.connect(investor).approve(await bond.getAddress(), partial);
    await bond.connect(investor).subscribe(partial);
    await time.increaseTo(issue + 1);
    await bond.completeIssuance();

    expect(await bond.totalSubscribed()).to.equal(partial);
    expect(await bond.totalSupply()).to.equal(partial);
  });

  it("발행 완료 후 청약 불가", async function () {
    const { bond, usdc, investor, investor2, issue } = await deployCouponBond();
    const amount = ethers.parseUnits("1000", 6);

    await usdc.connect(investor).approve(await bond.getAddress(), amount);
    await bond.connect(investor).subscribe(amount);
    await time.increaseTo(issue + 1);
    await bond.completeIssuance();

    await usdc.connect(investor2).approve(await bond.getAddress(), amount);
    await expect(
      bond.connect(investor2).subscribe(amount)
    ).to.be.revertedWith("subscription closed");
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — Reserve", function () {

  it("발행자가 Reserve 적립 가능", async function () {
    const { bond, usdc, issuer, investor, issue } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, ethers.parseUnits("5000", 6), issue);

    const amount = ethers.parseUnits("500", 6);
    await usdc.connect(issuer).approve(await bond.getAddress(), amount);
    await bond.connect(issuer).reserve(amount);

    expect(await bond.reserveBalance()).to.equal(amount);
  });

  it("발행자가 아닌 사람은 Reserve 불가", async function () {
    const { bond, usdc, investor, issue } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, ethers.parseUnits("5000", 6), issue);

    await usdc.connect(investor).approve(await bond.getAddress(), ethers.parseUnits("100", 6));
    await expect(
      bond.connect(investor).reserve(ethers.parseUnits("100", 6))
    ).to.be.revertedWith("only issuer");
  });

  it("체크포인트 버퍼 전에는 Reserve 체크 불가", async function () {
    const { bond, usdc, investor, issue } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, ethers.parseUnits("5000", 6), issue);

    // payment1 = now+30일, buffer=7일 → 체크 가능 시점 = now+23일
    // 현재 = now+1일 → 아직 이름
    await expect(
      bond.checkReserveForPayment(0)
    ).to.be.revertedWith("too early for reserve check");
  });

  it("체크포인트 도달 후 Reserve 부족 시 opsWallet 공개", async function () {
    const { bond, usdc, investor, opsWallet, issue, payment1 } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    // Reserve 없이 체크포인트 도달 (payment1 - 7일)
    const checkDate = payment1 - 7 * 24 * 3600;
    await time.increaseTo(checkDate + 1);

    await bond.checkReserveForPayment(0);

    expect(await bond.opsWalletRevealed()).to.equal(true);
    expect(await bond.getOpsWallet()).to.equal(opsWallet.address);
  });

  it("Reserve 충분하면 opsWallet 비공개 유지", async function () {
    const { bond, usdc, issuer, investor, issue, payment1 } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    // Reserve 충분히 적립
    const required = NOTIONAL * COUPON / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), required);
    await bond.connect(issuer).reserve(required);

    const checkDate = payment1 - 7 * 24 * 3600;
    await time.increaseTo(checkDate + 1);
    await bond.checkReserveForPayment(0);

    expect(await bond.opsWalletRevealed()).to.equal(false);
    expect(await bond.getOpsWallet()).to.equal(ethers.ZeroAddress);
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 쿠폰 청구(claim, 이표채)", function () {

  async function setupForClaim() {
    const f = await deployCouponBond();
    const subscribeAmt = NOTIONAL;
    await subscribeAndIssue(f.bond, f.usdc, f.investor, subscribeAmt, f.issue);

    // Reserve 적립 (쿠폰 + 원금)
    const totalRequired = NOTIONAL * (COUPON + PRINCIPAL) / 1_000_000n;
    await f.usdc.connect(f.issuer).approve(await f.bond.getAddress(), totalRequired);
    await f.bond.connect(f.issuer).reserve(totalRequired);

    return f;
  }

  it("지급일 전에는 claim 불가", async function () {
    const { bond, investor } = await setupForClaim();
    await expect(bond.connect(investor).claim(0)).to.be.revertedWith("payment not yet due");
  });

  it("쿠폰 지급 후 토큰은 유지됨", async function () {
    const { bond, usdc, investor, payment1 } = await setupForClaim();
    await time.increaseTo(payment1 + 1);

    const tokensBefore = await bond.balanceOf(investor.address);
    const usdcBefore   = await usdc.balanceOf(investor.address);

    await bond.connect(investor).claim(0);

    const tokensAfter = await bond.balanceOf(investor.address);
    const usdcAfter   = await usdc.balanceOf(investor.address);

    expect(tokensAfter).to.equal(tokensBefore);  // 토큰 유지
    expect(usdcAfter - usdcBefore).to.equal(NOTIONAL * COUPON / 1_000_000n);
  });

  it("같은 회차 중복 claim 불가", async function () {
    const { bond, investor, payment1 } = await setupForClaim();
    await time.increaseTo(payment1 + 1);

    await bond.connect(investor).claim(0);
    await expect(bond.connect(investor).claim(0)).to.be.revertedWith("already claimed");
  });

  it("토큰 없는 사람은 claim 불가", async function () {
    const { bond, other, payment1 } = await setupForClaim();
    await time.increaseTo(payment1 + 1);
    await expect(bond.connect(other).claim(0)).to.be.revertedWith("no tokens");
  });

  it("원금 지급 시 토큰 소각됨", async function () {
    const { bond, usdc, investor, payment2 } = await setupForClaim();
    await time.increaseTo(payment2 + 1);

    // 쿠폰 먼저 청구
    await bond.connect(investor).claim(0);

    const tokensBefore = await bond.balanceOf(investor.address);
    expect(tokensBefore).to.be.gt(0);

    await bond.connect(investor).claim(1); // 원금

    expect(await bond.balanceOf(investor.address)).to.equal(0);
  });

  it("Reserve 부족 시 claim 불가", async function () {
    const { bond, usdc, investor, issue, payment1 } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);
    // Reserve 적립 없음
    await time.increaseTo(payment1 + 1);
    await expect(bond.connect(investor).claim(0)).to.be.revertedWith("insufficient reserve");
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 이중 지급 방지 (paymentCap)", function () {

  it("A가 쿠폰 청구 후 토큰 매도 → B는 같은 회차 claim 불가", async function () {
    const { bond, usdc, issuer, investor, investor2, issue, payment1 } =
      await deployCouponBond();

    // 투자자A: 6,000  투자자B: 4,000 청약
    const amtA = ethers.parseUnits("6000", 6);
    const amtB = ethers.parseUnits("4000", 6);
    await usdc.connect(investor).approve(await bond.getAddress(), amtA);
    await bond.connect(investor).subscribe(amtA);
    await usdc.connect(investor2).approve(await bond.getAddress(), amtB);
    await bond.connect(investor2).subscribe(amtB);

    await time.increaseTo(issue + 1);
    await bond.completeIssuance();

    // Reserve 적립
    const totalCoupon = NOTIONAL * COUPON / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), totalCoupon);
    await bond.connect(issuer).reserve(totalCoupon);

    await time.increaseTo(payment1 + 1);

    // A가 쿠폰 청구 후 전체 토큰을 B에게 전송
    await bond.connect(investor).claim(0);
    await bond.connect(investor).transfer(investor2.address, amtA);

    // B는 같은 회차(0) claim 시도 → paymentCap 초과로 실패
    await expect(
      bond.connect(investor2).claim(0)
    ).to.be.revertedWith("payment cap exceeded");
  });

  it("두 투자자가 각자 몫만큼 정상 청구", async function () {
    const { bond, usdc, issuer, investor, investor2, issue, payment1 } =
      await deployCouponBond();

    const amtA = ethers.parseUnits("6000", 6);
    const amtB = ethers.parseUnits("4000", 6);
    await usdc.connect(investor).approve(await bond.getAddress(), amtA);
    await bond.connect(investor).subscribe(amtA);
    await usdc.connect(investor2).approve(await bond.getAddress(), amtB);
    await bond.connect(investor2).subscribe(amtB);

    await time.increaseTo(issue + 1);
    await bond.completeIssuance();

    const totalCoupon = NOTIONAL * COUPON / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), totalCoupon);
    await bond.connect(issuer).reserve(totalCoupon);

    await time.increaseTo(payment1 + 1);

    const usdcA_before = await usdc.balanceOf(investor.address);
    const usdcB_before = await usdc.balanceOf(investor2.address);

    await bond.connect(investor).claim(0);
    await bond.connect(investor2).claim(0);

    const usdcA_after = await usdc.balanceOf(investor.address);
    const usdcB_after = await usdc.balanceOf(investor2.address);

    expect(usdcA_after - usdcA_before).to.equal(amtA * COUPON / 1_000_000n);
    expect(usdcB_after - usdcB_before).to.equal(amtB * COUPON / 1_000_000n);
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 무이표채(Zero Coupon)", function () {

  it("만기에 원금+이자 일괄 수령 + 토큰 소각", async function () {
    const { bond, usdc, issuer, investor, issue, maturity } =
      await deployZeroCouponBond();

    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    // Reserve: 원금+이자
    const required = NOTIONAL * PRINCIPAL / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), required);
    await bond.connect(issuer).reserve(required);

    await time.increaseTo(maturity + 1);

    const usdcBefore = await usdc.balanceOf(investor.address);
    await bond.connect(investor).claim(0);
    const usdcAfter  = await usdc.balanceOf(investor.address);

    expect(usdcAfter - usdcBefore).to.equal(required);
    expect(await bond.balanceOf(investor.address)).to.equal(0); // 소각
  });

  it("만기 전 claim 불가", async function () {
    const { bond, usdc, issuer, investor, issue } = await deployZeroCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    const required = NOTIONAL * PRINCIPAL / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), required);
    await bond.connect(issuer).reserve(required);

    await expect(bond.connect(investor).claim(0)).to.be.revertedWith("payment not yet due");
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 경과이자 조회", function () {

  it("발행 전에는 경과이자 0", async function () {
    const { bond } = await deployCouponBond();
    expect(await bond.accruedInterestPerToken()).to.equal(0);
  });

  it("발행 완료 후 시간이 지나면 경과이자 > 0", async function () {
    const { bond, usdc, investor, issue } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    await time.increase(10 * 24 * 3600); // +10일

    const accrued = await bond.accruedInterestPerToken();
    expect(accrued).to.be.gt(0);
  });

  it("쿠폰 지급일 이후에는 그 시점부터 재기산", async function () {
    const { bond, usdc, issuer, investor, issue, payment1 } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    const couponTotal = NOTIONAL * COUPON / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), couponTotal * 2n);
    await bond.connect(issuer).reserve(couponTotal * 2n);

    // payment1 직전 경과이자
    await time.increaseTo(payment1 - 1);
    const accruedBefore = await bond.accruedInterestPerToken();

    // payment1 직후 경과이자 → 재기산으로 줄어야 함
    await time.increaseTo(payment1 + 1);
    const accruedAfter = await bond.accruedInterestPerToken();

    expect(accruedAfter).to.be.lt(accruedBefore);
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 잉여 Reserve 회수", function () {

  it("모든 지급 완료 후 잉여 Reserve 회수", async function () {
    const { bond, usdc, issuer, investor, issue, payment1, payment2 } =
      await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    // Reserve 과적립 (필요량의 2배)
    const excess = ethers.parseUnits("5000", 6);
    const needed = NOTIONAL * (COUPON + PRINCIPAL) / 1_000_000n;
    const total  = needed + excess;
    await usdc.connect(issuer).approve(await bond.getAddress(), total);
    await bond.connect(issuer).reserve(total);

    await time.increaseTo(payment1 + 1);
    await bond.connect(investor).claim(0);

    await time.increaseTo(payment2 + 1);
    await bond.connect(investor).claim(1);

    // 모든 토큰 소각 → totalSupply = 0 → required = 0
    const issuerBefore = await usdc.balanceOf(issuer.address);
    await bond.connect(issuer).withdrawExcessReserve();
    const issuerAfter  = await usdc.balanceOf(issuer.address);

    expect(issuerAfter).to.be.gt(issuerBefore);
  });

  it("잉여 없으면 회수 불가", async function () {
    const { bond, usdc, issuer, investor, issue, payment1 } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    // 딱 필요한 만큼만 적립
    const exact = NOTIONAL * COUPON / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), exact);
    await bond.connect(issuer).reserve(exact);

    await time.increaseTo(payment1 + 1);

    await expect(
      bond.connect(issuer).withdrawExcessReserve()
    ).to.be.revertedWith("no excess reserve");
  });
});

// ─────────────────────────────────────────────────────────────
describe("StructuredBond — 발행자 이전", function () {

  it("발행자가 주소를 이전하면 새 발행자만 reserve 가능", async function () {
    const { bond, usdc, issuer, investor, other, issue } = await deployCouponBond();
    await subscribeAndIssue(bond, usdc, investor, NOTIONAL, issue);

    await bond.connect(issuer).transferIssuer(other.address);
    expect(await bond.issuer()).to.equal(other.address);

    // 기존 발행자 reserve 시도 → 실패
    await usdc.connect(issuer).approve(await bond.getAddress(), ethers.parseUnits("100", 6));
    await expect(
      bond.connect(issuer).reserve(ethers.parseUnits("100", 6))
    ).to.be.revertedWith("only issuer");

    // 새 발행자 reserve → 성공
    await usdc.mint(other.address, ethers.parseUnits("100", 6));
    await usdc.connect(other).approve(await bond.getAddress(), ethers.parseUnits("100", 6));
    await bond.connect(other).reserve(ethers.parseUnits("100", 6));
    expect(await bond.reserveBalance()).to.equal(ethers.parseUnits("100", 6));
  });
});
