const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time }   = require("@nomicfoundation/hardhat-network-helpers");

describe("BondFactory", function () {

  async function deployFixture() {
    const [owner, issuer, issuer2, opsWallet, investor] = await ethers.getSigners();

    // MockUSDC 배포
    const MockUSDC = await ethers.getContractFactory("MockUSDC");
    const usdc = await MockUSDC.deploy();

    // BondFactory 배포 (owner가 배포)
    const Factory = await ethers.getContractFactory("BondFactory");
    const factory = await Factory.connect(owner).deploy();

    // USDC 화이트리스트 등록
    await factory.connect(owner).setAllowedUSDC(await usdc.getAddress(), true);

    const NOTIONAL    = ethers.parseUnits("10000", 6);
    const COUPON_BPS  = 1000;
    const MATURITY_TS = (await time.latest()) + 7 * 24 * 60 * 60;

    return { factory, usdc, owner, issuer, issuer2, opsWallet, investor,
             NOTIONAL, COUPON_BPS, MATURITY_TS };
  }

  // 채권 생성 헬퍼
  async function createBond(factory, usdc, issuer, opsWallet, params = {}) {
    const MATURITY_TS = params.maturityTs || (await time.latest()) + 7 * 24 * 60 * 60;
    const tx = await factory.connect(issuer).createBond(
      params.name      || "TEST-BOND",
      params.symbol    || "TBND",
      await usdc.getAddress(),
      opsWallet.address,
      params.notional  || ethers.parseUnits("10000", 6),
      params.couponBps || 1000,
      MATURITY_TS
    );
    const receipt = await tx.wait();
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
    });

    it("발행된 토큰이 발행자에게 전달되어야 한다", async function () {
      const { factory, usdc, issuer, opsWallet, NOTIONAL } = await deployFixture();
      const bondAddress = await createBond(factory, usdc, issuer, opsWallet);
      const bond = await ethers.getContractAt("StructuredBond", bondAddress);

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
      ).to.emit(factory, "BondCreated");
    });

    it("화이트리스트에 없는 USDC로 생성하면 실패", async function () {
      const { factory, issuer, opsWallet, MATURITY_TS } = await deployFixture();
      const fakeUSDC = ethers.Wallet.createRandom().address;

      await expect(
        factory.connect(issuer).createBond(
          "TEST-BOND", "TBND",
          fakeUSDC,
          opsWallet.address,
          ethers.parseUnits("10000", 6), 1000, MATURITY_TS
        )
      ).to.be.revertedWith("usdc not whitelisted");
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

  // ── 2. USDC 화이트리스트 ─────────────────────────────────
  describe("USDC 화이트리스트", function () {

    it("owner만 화이트리스트 등록 가능", async function () {
      const { factory, issuer } = await deployFixture();
      const fakeToken = ethers.Wallet.createRandom().address;

      await expect(
        factory.connect(issuer).setAllowedUSDC(fakeToken, true)
      ).to.be.revertedWith("only owner");
    });

    it("화이트리스트 해제 후 채권 생성 불가", async function () {
      const { factory, usdc, owner, issuer, opsWallet, MATURITY_TS } = await deployFixture();

      // 화이트리스트 해제
      await factory.connect(owner).setAllowedUSDC(await usdc.getAddress(), false);

      await expect(
        factory.connect(issuer).createBond(
          "TEST-BOND", "TBND",
          await usdc.getAddress(),
          opsWallet.address,
          ethers.parseUnits("10000", 6), 1000, MATURITY_TS
        )
      ).to.be.revertedWith("usdc not whitelisted");
    });
  });

  // ── 3. 목록 관리 ─────────────────────────────────────────
  describe("목록 관리", function () {

    it("생성한 채권이 allBonds에 추가되어야 한다", async function () {
      const { factory, usdc, issuer, opsWallet } = await deployFixture();

      expect(await factory.totalBonds()).to.equal(0);
      await createBond(factory, usdc, issuer, opsWallet, { name: "B1", symbol: "B1" });
      await createBond(factory, usdc, issuer, opsWallet, { name: "B2", symbol: "B2" });
      expect(await factory.totalBonds()).to.equal(2);
    });

    it("발행자별 채권 목록이 따로 관리되어야 한다", async function () {
      const { factory, usdc, issuer, issuer2, opsWallet } = await deployFixture();

      await createBond(factory, usdc, issuer,  opsWallet, { name: "A", symbol: "A" });
      await createBond(factory, usdc, issuer,  opsWallet, { name: "B", symbol: "B" });
      await createBond(factory, usdc, issuer2, opsWallet, { name: "C", symbol: "C" });

      expect((await factory.getBondsByIssuer(issuer.address)).length).to.equal(2);
      expect((await factory.getBondsByIssuer(issuer2.address)).length).to.equal(1);
    });
  });

  // ── 4. E2E ───────────────────────────────────────────────
  describe("E2E — Factory로 생성한 채권 전체 흐름", function () {

    it("reserve → redeem 정상 동작", async function () {
      const { factory, usdc, issuer, opsWallet, investor } = await deployFixture();
      const MATURITY_TS = (await time.latest()) + 7 * 24 * 60 * 60;

      const bondAddress = await createBond(factory, usdc, issuer, opsWallet, { maturityTs: MATURITY_TS });
      const bond = await ethers.getContractAt("StructuredBond", bondAddress);

      await usdc.mint(issuer.address, ethers.parseUnits("100000", 6));

      const reserveAmt = ethers.parseUnits("10020", 6);
      await usdc.connect(issuer).approve(bondAddress, reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);
      await bond.connect(issuer).transfer(investor.address, ethers.parseUnits("1000", 6));

      await time.increaseTo(MATURITY_TS + 1);

      const before = await usdc.balanceOf(investor.address);
      await bond.connect(investor).redeem();
      const after  = await usdc.balanceOf(investor.address);

      expect(after - before).to.be.gt(ethers.parseUnits("1000", 6));
    });

    it("잉여 Reserve를 발행자가 회수할 수 있다", async function () {
      const { factory, usdc, issuer, opsWallet, investor } = await deployFixture();
      const MATURITY_TS = (await time.latest()) + 7 * 24 * 60 * 60;

      const bondAddress = await createBond(factory, usdc, issuer, opsWallet, { maturityTs: MATURITY_TS });
      const bond = await ethers.getContractAt("StructuredBond", bondAddress);

      await usdc.mint(issuer.address, ethers.parseUnits("100000", 6));

      // Reserve를 필요량보다 많이 적립
      const reserveAmt = ethers.parseUnits("20000", 6); // 2배 적립
      await usdc.connect(issuer).approve(bondAddress, reserveAmt);
      await bond.connect(issuer).reserve(reserveAmt);

      // 투자자 1명만 1000토큰 구매 후 만기 redeem
      await bond.connect(issuer).transfer(investor.address, ethers.parseUnits("1000", 6));
      await time.increaseTo(MATURITY_TS + 1);
      await bond.connect(investor).redeem();

      // 발행자가 잉여 Reserve 회수
      const issuerBefore = await usdc.balanceOf(issuer.address);
      await bond.connect(issuer).withdrawExcessReserve();
      const issuerAfter  = await usdc.balanceOf(issuer.address);

      expect(issuerAfter).to.be.gt(issuerBefore);
    });

    it("발행자 주소를 이전할 수 있다", async function () {
      const { factory, usdc, issuer, opsWallet, investor } = await deployFixture();
      const bondAddress = await createBond(factory, usdc, issuer, opsWallet);
      const bond = await ethers.getContractAt("StructuredBond", bondAddress);

      await bond.connect(issuer).transferIssuer(investor.address);
      expect(await bond.issuer()).to.equal(investor.address);

      // 기존 발행자는 reserve 불가
      await usdc.mint(issuer.address, ethers.parseUnits("10020", 6));
      await usdc.connect(issuer).approve(bondAddress, ethers.parseUnits("10020", 6));
      await expect(
        bond.connect(issuer).reserve(ethers.parseUnits("10020", 6))
      ).to.be.revertedWith("only issuer");
    });
  });
});
