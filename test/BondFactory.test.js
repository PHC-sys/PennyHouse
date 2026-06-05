const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time }   = require("@nomicfoundation/hardhat-network-helpers");

describe("BondFactory", function () {

  async function deployFixture() {
    const [issuer, issuer2, opsWallet, investor] = await ethers.getSigners();

    // MockUSDC 배포
    const MockUSDC = await ethers.getContractFactory("MockUSDC");
    const usdc = await MockUSDC.deploy();

    // BondFactory 배포
    const Factory = await ethers.getContractFactory("BondFactory");
    const factory = await Factory.deploy();

    // 기본 채권 파라미터
    const NOTIONAL    = ethers.parseUnits("10000", 6);
    const COUPON_BPS  = 1000;
    const MATURITY_TS = (await time.latest()) + 7 * 24 * 60 * 60;

    return { factory, usdc, issuer, issuer2, opsWallet, investor,
             NOTIONAL, COUPON_BPS, MATURITY_TS };
  }

  // 채권 생성 헬퍼 (반복 줄이기)
  async function createBond(factory, usdc, issuer, opsWallet, params = {}) {
    const MATURITY_TS = params.maturityTs || (await time.latest()) + 7 * 24 * 60 * 60;
    const tx = await factory.connect(issuer).createBond(
      params.name        || "TEST-BOND",
      params.symbol      || "TBND",
      await usdc.getAddress(),
      opsWallet.address,
      params.notional    || ethers.parseUnits("10000", 6),
      params.couponBps   || 1000,
      MATURITY_TS
    );
    const receipt = await tx.wait();
    // BondCreated 이벤트에서 채권 주소 추출
    const event = receipt.logs.find(
      log => log.fragment && log.fragment.name === "BondCreated"
    );
    return event.args.bondAddress;
  }

  // ── 1. 채권 생성 ─────────────────────────────────────────
  describe("createBond()", function () {

    it("채권 컨트랙트가 새로 배포되어야 한다", async function () {
      const { factory, usdc, issuer, opsWallet } = await deployFixture();

      const bondAddress = await createBond(factory, usdc, issuer, opsWallet);

      expect(bondAddress).to.be.properAddress;
      expect(bondAddress).to.not.equal(ethers.ZeroAddress);
    });

    it("발행된 토큰이 발행자(msg.sender)에게 전달되어야 한다", async function () {
      const { factory, usdc, issuer, opsWallet, NOTIONAL } = await deployFixture();

      const bondAddress = await createBond(factory, usdc, issuer, opsWallet);
      const bond = await ethers.getContractAt("StructuredBond", bondAddress);

      // Factory가 아닌 issuer(tx 호출자)가 토큰을 보유해야 함
      expect(await bond.balanceOf(issuer.address)).to.equal(NOTIONAL);
      expect(await bond.balanceOf(await factory.getAddress())).to.equal(0);
    });

    it("채권 조건이 파라미터대로 설정되어야 한다", async function () {
      const { factory, usdc, issuer, opsWallet, NOTIONAL, COUPON_BPS, MATURITY_TS } = await deployFixture();

      const bondAddress = await createBond(factory, usdc, issuer, opsWallet, {
        notional: NOTIONAL, couponBps: COUPON_BPS, maturityTs: MATURITY_TS
      });
      const bond = await ethers.getContractAt("StructuredBond", bondAddress);

      expect(await bond.notional()).to.equal(NOTIONAL);
      expect(await bond.couponRateBps()).to.equal(COUPON_BPS);
      expect(await bond.maturityDate()).to.equal(MATURITY_TS);
    });

    it("BondCreated 이벤트가 발생해야 한다", async function () {
      const { factory, usdc, issuer, opsWallet, NOTIONAL, COUPON_BPS, MATURITY_TS } = await deployFixture();

      await expect(
        factory.connect(issuer).createBond(
          "TEST-BOND", "TBND",
          await usdc.getAddress(),
          opsWallet.address,
          NOTIONAL, COUPON_BPS, MATURITY_TS
        )
      ).to.emit(factory, "BondCreated")
       .withArgs(
         issuer.address,
         (val) => ethers.isAddress(val), // 채권 주소 (동적 값)
         "TEST-BOND", "TBND",
         NOTIONAL, COUPON_BPS, MATURITY_TS
       );
    });

    it("name 없이 생성하면 실패", async function () {
      const { factory, usdc, issuer, opsWallet, MATURITY_TS } = await deployFixture();

      await expect(
        factory.connect(issuer).createBond(
          "", "TBND",
          await usdc.getAddress(),
          opsWallet.address,
          ethers.parseUnits("10000", 6), 1000, MATURITY_TS
        )
      ).to.be.revertedWith("name required");
    });

    it("symbol 없이 생성하면 실패", async function () {
      const { factory, usdc, issuer, opsWallet, MATURITY_TS } = await deployFixture();

      await expect(
        factory.connect(issuer).createBond(
          "TEST-BOND", "",
          await usdc.getAddress(),
          opsWallet.address,
          ethers.parseUnits("10000", 6), 1000, MATURITY_TS
        )
      ).to.be.revertedWith("symbol required");
    });

    it("과거 만기일로 생성하면 실패", async function () {
      const { factory, usdc, issuer, opsWallet } = await deployFixture();
      const pastTs = (await time.latest()) - 1000;

      await expect(
        factory.connect(issuer).createBond(
          "TEST-BOND", "TBND",
          await usdc.getAddress(),
          opsWallet.address,
          ethers.parseUnits("10000", 6), 1000, pastTs
        )
      ).to.be.revertedWith("maturity must be in the future");
    });
  });

  // ── 2. 목록 관리 ─────────────────────────────────────────
  describe("목록 관리", function () {

    it("생성한 채권이 allBonds 목록에 추가되어야 한다", async function () {
      const { factory, usdc, issuer, opsWallet } = await deployFixture();

      expect(await factory.totalBonds()).to.equal(0);

      const addr1 = await createBond(factory, usdc, issuer, opsWallet, { name: "BOND-1", symbol: "B1" });
      expect(await factory.totalBonds()).to.equal(1);

      const addr2 = await createBond(factory, usdc, issuer, opsWallet, { name: "BOND-2", symbol: "B2" });
      expect(await factory.totalBonds()).to.equal(2);

      const all = await factory.getAllBonds();
      expect(all[0]).to.equal(addr1);
      expect(all[1]).to.equal(addr2);
    });

    it("발행자별 채권 목록이 따로 관리되어야 한다", async function () {
      const { factory, usdc, issuer, issuer2, opsWallet } = await deployFixture();

      // issuer1 채권 2개
      await createBond(factory, usdc, issuer,  opsWallet, { name: "BOND-A", symbol: "BA" });
      await createBond(factory, usdc, issuer,  opsWallet, { name: "BOND-B", symbol: "BB" });
      // issuer2 채권 1개
      await createBond(factory, usdc, issuer2, opsWallet, { name: "BOND-C", symbol: "BC" });

      const bonds1 = await factory.getBondsByIssuer(issuer.address);
      const bonds2 = await factory.getBondsByIssuer(issuer2.address);

      expect(bonds1.length).to.equal(2);
      expect(bonds2.length).to.equal(1);
      expect(await factory.totalBonds()).to.equal(3);
    });

    it("배포한 적 없는 주소의 목록은 빈 배열", async function () {
      const { factory, investor } = await deployFixture();

      const bonds = await factory.getBondsByIssuer(investor.address);
      expect(bonds.length).to.equal(0);
    });
  });

  // ── 3. 채권 생성 후 실제 동작 (E2E) ─────────────────────
  describe("E2E — Factory로 생성한 채권 실제 사용", function () {

    it("Factory로 만든 채권에서 reserve → redeem 전체 흐름", async function () {
      const { factory, usdc, issuer, opsWallet, investor } = await deployFixture();
      const MATURITY_TS = (await time.latest()) + 7 * 24 * 60 * 60;

      // 1. Factory로 채권 생성
      const bondAddress = await createBond(factory, usdc, issuer, opsWallet, {
        maturityTs: MATURITY_TS
      });
      const bond = await ethers.getContractAt("StructuredBond", bondAddress);

      // 2. USDC 민팅 (테스트용)
      await usdc.mint(issuer.address, ethers.parseUnits("100000", 6));

      // 3. Reserve 적립
      const reserveAmt = ethers.parseUnits("10020", 6);
      await usdc.connect(issuer).approve(bondAddress, reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);

      // 4. 투자자에게 토큰 전송
      await bond.connect(issuer).transfer(investor.address, ethers.parseUnits("1000", 6));

      // 5. 만기일로 시간 이동
      await time.increaseTo(MATURITY_TS + 1);

      // 6. 투자자 redeem
      const before = await usdc.balanceOf(investor.address);
      await bond.connect(investor).redeem();
      const after  = await usdc.balanceOf(investor.address);

      expect(after - before).to.be.gt(ethers.parseUnits("1000", 6)); // 원금 + 이자
      expect(await bond.balanceOf(investor.address)).to.equal(0);     // 토큰 소각
    });
  });
});
