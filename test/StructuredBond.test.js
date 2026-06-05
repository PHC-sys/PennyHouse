const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time }   = require("@nomicfoundation/hardhat-network-helpers");

describe("StructuredBond", function () {

  async function deployFixture() {
    const [issuer, investor, opsWallet, other] = await ethers.getSigners();

    // MockUSDC 배포
    const MockUSDC = await ethers.getContractFactory("MockUSDC");
    const usdc = await MockUSDC.deploy();

    // 채권 파라미터
    const NOTIONAL       = ethers.parseUnits("10000", 6);  // 10,000 USDC
    const COUPON_BPS     = 1000;                            // 연 10%
    const now            = await time.latest();
    const MATURITY_TS    = now + 7 * 24 * 60 * 60;         // 지금으로부터 7일 후 timestamp

    // StructuredBond 배포
    const Bond = await ethers.getContractFactory("StructuredBond");
    const bond = await Bond.deploy(
      "TEST-BOND",
      "TBND",
      await usdc.getAddress(),
      opsWallet.address,
      NOTIONAL,
      COUPON_BPS,
      MATURITY_TS       // ← 날짜(timestamp) 직접 입력
    );

    // 발행자에게 USDC 지급 (테스트용)
    await usdc.mint(issuer.address, ethers.parseUnits("100000", 6));

    return { bond, usdc, issuer, investor, opsWallet, other, NOTIONAL, COUPON_BPS, MATURITY_TS };
  }

  // ── 1. 배포 확인 ─────────────────────────────────────────
  describe("배포", function () {
    it("채권 조건이 올바르게 설정되어야 한다", async function () {
      const { bond, NOTIONAL, COUPON_BPS, MATURITY_TS } = await deployFixture();

      expect(await bond.notional()).to.equal(NOTIONAL);
      expect(await bond.couponRateBps()).to.equal(COUPON_BPS);
      expect(await bond.maturityDate()).to.equal(MATURITY_TS);
      expect(await bond.settled()).to.equal(false);
    });

    it("발행자에게 토큰이 전량 발행되어야 한다", async function () {
      const { bond, issuer, NOTIONAL } = await deployFixture();

      expect(await bond.balanceOf(issuer.address)).to.equal(NOTIONAL);
      expect(await bond.totalSupply()).to.equal(NOTIONAL);
    });

    it("paymentPerToken이 원금보다 커야 한다", async function () {
      const { bond } = await deployFixture();

      const payment = await bond.paymentPerToken();
      expect(payment).to.be.gt(ethers.parseUnits("1", 6));
    });

    it("과거 날짜를 만기일로 설정하면 배포 실패", async function () {
      const [issuer, , opsWallet] = await ethers.getSigners();
      const MockUSDC = await ethers.getContractFactory("MockUSDC");
      const usdc = await MockUSDC.deploy();

      const pastTimestamp = (await time.latest()) - 1000; // 과거

      const Bond = await ethers.getContractFactory("StructuredBond");
      await expect(
        Bond.deploy(
          "BAD-BOND", "BAD",
          await usdc.getAddress(),
          opsWallet.address,
          ethers.parseUnits("10000", 6),
          1000,
          pastTimestamp  // ← 과거 날짜
        )
      ).to.be.revertedWith("maturity must be in the future");
    });
  });

  // ── 2. Reserve 적립 ──────────────────────────────────────
  describe("reserve()", function () {
    it("발행자가 Reserve를 적립할 수 있다", async function () {
      const { bond, usdc, issuer } = await deployFixture();
      const amount = ethers.parseUnits("10020", 6);

      await usdc.connect(issuer).approve(await bond.getAddress(), amount);
      await bond.connect(issuer).reserve(amount);

      expect(await bond.reserveBalance()).to.equal(amount);
    });

    it("발행자가 아닌 사람은 reserve 불가", async function () {
      const { bond, usdc, investor } = await deployFixture();
      await usdc.mint(investor.address, ethers.parseUnits("10020", 6));
      await usdc.connect(investor).approve(await bond.getAddress(), ethers.parseUnits("10020", 6));

      await expect(
        bond.connect(investor).reserve(ethers.parseUnits("10020", 6))
      ).to.be.revertedWith("only issuer");
    });

    it("amount 0 입력 시 실패", async function () {
      const { bond, usdc, issuer } = await deployFixture();
      await usdc.connect(issuer).approve(await bond.getAddress(), 1000);

      await expect(
        bond.connect(issuer).reserve(0)
      ).to.be.revertedWith("amount must be > 0");
    });

    it("Reserve 충분하면 opsWallet 비공개 유지", async function () {
      const { bond, usdc, issuer } = await deployFixture();
      const amount = ethers.parseUnits("10020", 6);

      await usdc.connect(issuer).approve(await bond.getAddress(), amount);
      await bond.connect(issuer).reserve(amount);

      const status = await bond.getReserveStatus();
      expect(status._sufficient).to.equal(true);
      expect(status._opsRevealed).to.equal(false);
    });

    it("Reserve 부족하면 opsWallet 자동 공개", async function () {
      const { bond, usdc, issuer, opsWallet } = await deployFixture();
      const smallAmount = ethers.parseUnits("100", 6);

      await usdc.connect(issuer).approve(await bond.getAddress(), smallAmount);
      await bond.connect(issuer).reserve(smallAmount);

      const status = await bond.getReserveStatus();
      expect(status._sufficient).to.equal(false);
      expect(status._opsRevealed).to.equal(true);
      expect(status._opsWallet).to.equal(opsWallet.address);
    });
  });

  // ── 3. 만기 상환 ─────────────────────────────────────────
  describe("redeem()", function () {
    it("만기 전에는 redeem 불가", async function () {
      const { bond, usdc, issuer, investor } = await deployFixture();

      const reserveAmt = ethers.parseUnits("10020", 6);
      await usdc.connect(issuer).approve(await bond.getAddress(), reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);
      await bond.connect(issuer).transfer(investor.address, ethers.parseUnits("1000", 6));

      await expect(
        bond.connect(investor).redeem()
      ).to.be.revertedWith("not matured yet");
    });

    it("만기 후 토큰 burn → USDC 수령 (원금 + 이자)", async function () {
      const { bond, usdc, issuer, investor, MATURITY_TS } = await deployFixture();

      const investAmount = ethers.parseUnits("1000", 6);
      const reserveAmt   = ethers.parseUnits("10020", 6);

      await usdc.connect(issuer).approve(await bond.getAddress(), reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);
      await bond.connect(issuer).transfer(investor.address, investAmount);

      // 만기일로 시간 이동
      await time.increaseTo(MATURITY_TS + 1);

      const usdcBefore = await usdc.balanceOf(investor.address);
      await bond.connect(investor).redeem();
      const usdcAfter  = await usdc.balanceOf(investor.address);

      expect(usdcAfter).to.be.gt(usdcBefore);
      expect(usdcAfter - usdcBefore).to.be.gt(investAmount); // 이자 포함
      expect(await bond.balanceOf(investor.address)).to.equal(0); // 토큰 소각
    });

    it("Reserve 부족하면 redeem 불가", async function () {
      const { bond, issuer, investor, MATURITY_TS } = await deployFixture();

      await bond.connect(issuer).transfer(investor.address, ethers.parseUnits("1000", 6));
      await time.increaseTo(MATURITY_TS + 1);

      await expect(
        bond.connect(investor).redeem()
      ).to.be.revertedWith("insufficient reserve");
    });

    it("토큰 없는 사람은 redeem 불가", async function () {
      const { bond, usdc, issuer, other, MATURITY_TS } = await deployFixture();

      const reserveAmt = ethers.parseUnits("10020", 6);
      await usdc.connect(issuer).approve(await bond.getAddress(), reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);
      await time.increaseTo(MATURITY_TS + 1);

      await expect(
        bond.connect(other).redeem()
      ).to.be.revertedWith("no tokens to redeem");
    });

    it("같은 사람이 redeem을 두 번 호출해도 두 번째는 실패", async function () {
      const { bond, usdc, issuer, investor, MATURITY_TS } = await deployFixture();

      const reserveAmt = ethers.parseUnits("10020", 6);
      await usdc.connect(issuer).approve(await bond.getAddress(), reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);
      await bond.connect(issuer).transfer(investor.address, ethers.parseUnits("1000", 6));
      await time.increaseTo(MATURITY_TS + 1);

      await bond.connect(investor).redeem();     // 첫 번째: 성공
      await expect(
        bond.connect(investor).redeem()          // 두 번째: 토큰 없으므로 실패
      ).to.be.revertedWith("no tokens to redeem");
    });
  });

  // ── 4. 2차 시장 ──────────────────────────────────────────
  describe("2차 시장", function () {
    it("토큰 전송으로 청구권이 이전된다", async function () {
      const { bond, usdc, issuer, investor, other, MATURITY_TS } = await deployFixture();

      const reserveAmt = ethers.parseUnits("10020", 6);
      await usdc.connect(issuer).approve(await bond.getAddress(), reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);

      await bond.connect(issuer).transfer(investor.address, ethers.parseUnits("1000", 6));
      await bond.connect(investor).transfer(other.address, ethers.parseUnits("600", 6));

      await time.increaseTo(MATURITY_TS + 1);

      const before = await usdc.balanceOf(other.address);
      await bond.connect(other).redeem();
      const after  = await usdc.balanceOf(other.address);

      expect(after - before).to.be.gt(ethers.parseUnits("600", 6));
    });
  });
});
