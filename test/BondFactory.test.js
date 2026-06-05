const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time }   = require("@nomicfoundation/hardhat-network-helpers");

const NOTIONAL  = ethers.parseUnits("10000", 6);
const COUPON    = 50_000n;
const PRINCIPAL = 1_050_000n;

async function deployFactoryFixture() {
  const [owner, issuer, issuer2, investor, opsWallet, other] =
    await ethers.getSigners();

  const MockUSDC = await ethers.getContractFactory("MockUSDC");
  const usdc = await MockUSDC.deploy();

  const Factory = await ethers.getContractFactory("BondFactory");
  const factory = await Factory.connect(owner).deploy();

  // USDC 화이트리스트 등록
  await factory.connect(owner).setAllowedUSDC(await usdc.getAddress(), true);

  await usdc.mint(issuer.address,   ethers.parseUnits("1000000", 6));
  await usdc.mint(investor.address, ethers.parseUnits("100000",  6));

  const now      = await time.latest();
  const subStart = now;
  const issue    = now + 1  * 24 * 3600;
  const payment1 = now + 30 * 24 * 3600;
  const payment2 = now + 60 * 24 * 3600;

  // 기본 BondParams
  const defaultParams = {
    name:              "FACTORY-BOND-001",
    symbol:            "FB001",
    opsWallet:         opsWallet.address,
    maxNotional:       NOTIONAL,
    couponRateBps:     1000,
    subscriptionStart: subStart,
    issueDate:         issue,
    reserveBufferDays: 7,
    paymentDates:      [payment1, payment2],
    amountsPerToken:   [COUPON, PRINCIPAL],
    isPrincipal:       [false, true],
  };

  return {
    factory, usdc, owner, issuer, issuer2, investor, opsWallet, other,
    defaultParams, issue, payment1, payment2
  };
}

// ─────────────────────────────────────────────────────────────
describe("BondFactory — 채권 생성", function () {

  it("createBond() 후 채권 컨트랙트가 배포됨", async function () {
    const { factory, usdc, issuer, defaultParams } = await deployFactoryFixture();
    const bondAddr = await factory.connect(issuer).createBond.staticCall(
      await usdc.getAddress(), defaultParams
    );
    await factory.connect(issuer).createBond(await usdc.getAddress(), defaultParams);

    expect(bondAddr).to.be.properAddress;
    expect(await factory.totalBonds()).to.equal(1);
  });

  it("issuer가 채권의 issuer로 등록됨", async function () {
    const { factory, usdc, issuer, defaultParams } = await deployFactoryFixture();

    const tx = await factory.connect(issuer).createBond(
      await usdc.getAddress(), defaultParams
    );
    const receipt = await tx.wait();
    const event   = receipt.logs.find(l => l.fragment?.name === "BondCreated");
    const bondAddr = event.args.bondAddress;
    const bond = await ethers.getContractAt("StructuredBond", bondAddr);

    expect(await bond.issuer()).to.equal(issuer.address);
  });

  it("화이트리스트에 없는 USDC → 실패", async function () {
    const { factory, issuer, defaultParams } = await deployFactoryFixture();
    const fakeUSDC = ethers.Wallet.createRandom().address;

    await expect(
      factory.connect(issuer).createBond(fakeUSDC, defaultParams)
    ).to.be.revertedWith("usdc not whitelisted");
  });

  it("name 비어있으면 실패", async function () {
    const { factory, usdc, issuer, defaultParams } = await deployFactoryFixture();
    await expect(
      factory.connect(issuer).createBond(await usdc.getAddress(), {
        ...defaultParams, name: ""
      })
    ).to.be.revertedWith("name required");
  });

  it("BondCreated 이벤트 발생", async function () {
    const { factory, usdc, issuer, defaultParams } = await deployFactoryFixture();
    await expect(
      factory.connect(issuer).createBond(await usdc.getAddress(), defaultParams)
    ).to.emit(factory, "BondCreated");
  });
});

// ─────────────────────────────────────────────────────────────
describe("BondFactory — USDC 화이트리스트", function () {

  it("owner만 화이트리스트 등록 가능", async function () {
    const { factory, issuer } = await deployFactoryFixture();
    const fakeToken = ethers.Wallet.createRandom().address;
    await expect(
      factory.connect(issuer).setAllowedUSDC(fakeToken, true)
    ).to.be.revertedWith("only owner");
  });

  it("화이트리스트 해제 후 채권 생성 불가", async function () {
    const { factory, usdc, owner, issuer, defaultParams } = await deployFactoryFixture();
    await factory.connect(owner).setAllowedUSDC(await usdc.getAddress(), false);

    await expect(
      factory.connect(issuer).createBond(await usdc.getAddress(), defaultParams)
    ).to.be.revertedWith("usdc not whitelisted");
  });
});

// ─────────────────────────────────────────────────────────────
describe("BondFactory — 목록 관리", function () {

  it("발행자별 채권 목록 분리 관리", async function () {
    const { factory, usdc, issuer, issuer2, defaultParams } = await deployFactoryFixture();
    const now = await time.latest();

    const paramsA = { ...defaultParams, name: "BOND-A", symbol: "BA",
      subscriptionStart: now, issueDate: now + 3600,
      paymentDates: [now + 2 * 3600, now + 4 * 3600] };

    const paramsB = { ...defaultParams, name: "BOND-B", symbol: "BB",
      subscriptionStart: now, issueDate: now + 3600,
      paymentDates: [now + 2 * 3600, now + 4 * 3600] };

    const paramsC = { ...defaultParams, name: "BOND-C", symbol: "BC",
      subscriptionStart: now, issueDate: now + 3600,
      paymentDates: [now + 2 * 3600, now + 4 * 3600] };

    await factory.connect(issuer).createBond(await usdc.getAddress(), paramsA);
    await factory.connect(issuer).createBond(await usdc.getAddress(), paramsB);
    await factory.connect(issuer2).createBond(await usdc.getAddress(), paramsC);

    expect((await factory.getBondsByIssuer(issuer.address)).length).to.equal(2);
    expect((await factory.getBondsByIssuer(issuer2.address)).length).to.equal(1);
    expect(await factory.totalBonds()).to.equal(3);
  });

  it("처음 발행한 주소의 목록은 빈 배열", async function () {
    const { factory, other } = await deployFactoryFixture();
    expect((await factory.getBondsByIssuer(other.address)).length).to.equal(0);
  });
});

// ─────────────────────────────────────────────────────────────
describe("BondFactory — E2E (Factory 생성 채권 전체 흐름)", function () {

  it("이표채: 청약 → 발행 → 쿠폰 → 원금 전체 흐름", async function () {
    const { factory, usdc, issuer, investor, defaultParams, issue, payment1, payment2 } =
      await deployFactoryFixture();

    // 채권 생성
    const tx = await factory.connect(issuer).createBond(
      await usdc.getAddress(), defaultParams
    );
    const receipt  = await tx.wait();
    const event    = receipt.logs.find(l => l.fragment?.name === "BondCreated");
    const bond     = await ethers.getContractAt("StructuredBond", event.args.bondAddress);

    // 청약
    await usdc.connect(investor).approve(await bond.getAddress(), NOTIONAL);
    await bond.connect(investor).subscribe(NOTIONAL);

    // 발행 완료
    await time.increaseTo(issue + 1);
    await bond.completeIssuance();

    // Reserve 적립
    const totalReserve = NOTIONAL * (COUPON + PRINCIPAL) / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), totalReserve);
    await bond.connect(issuer).reserve(totalReserve);

    // 쿠폰 청구
    await time.increaseTo(payment1 + 1);
    const beforeCoupon = await usdc.balanceOf(investor.address);
    await bond.connect(investor).claim(0);
    const afterCoupon  = await usdc.balanceOf(investor.address);
    expect(afterCoupon - beforeCoupon).to.equal(NOTIONAL * COUPON / 1_000_000n);
    expect(await bond.balanceOf(investor.address)).to.equal(NOTIONAL); // 토큰 유지

    // 원금 청구
    await time.increaseTo(payment2 + 1);
    const beforePrincipal = await usdc.balanceOf(investor.address);
    await bond.connect(investor).claim(1);
    const afterPrincipal  = await usdc.balanceOf(investor.address);
    expect(afterPrincipal - beforePrincipal).to.equal(NOTIONAL * PRINCIPAL / 1_000_000n);
    expect(await bond.balanceOf(investor.address)).to.equal(0); // 소각
  });

  it("무이표채: 청약 → 발행 → 원금 일괄 상환", async function () {
    const { factory, usdc, owner, issuer, investor, opsWallet } =
      await deployFactoryFixture();

    const now      = await time.latest();
    const subStart = now;
    const issue    = now + 1  * 24 * 3600;
    const maturity = now + 60 * 24 * 3600;

    const zcParams = {
      name:              "ZC-BOND-001",
      symbol:            "ZC001",
      opsWallet:         opsWallet.address,
      maxNotional:       NOTIONAL,
      couponRateBps:     500,
      subscriptionStart: subStart,
      issueDate:         issue,
      reserveBufferDays: 3,
      paymentDates:      [maturity],
      amountsPerToken:   [PRINCIPAL],
      isPrincipal:       [true],
    };

    const tx      = await factory.connect(issuer).createBond(await usdc.getAddress(), zcParams);
    const receipt = await tx.wait();
    const event   = receipt.logs.find(l => l.fragment?.name === "BondCreated");
    const bond    = await ethers.getContractAt("StructuredBond", event.args.bondAddress);

    // 청약 + 발행
    await usdc.connect(investor).approve(await bond.getAddress(), NOTIONAL);
    await bond.connect(investor).subscribe(NOTIONAL);
    await time.increaseTo(issue + 1);
    await bond.completeIssuance();

    // Reserve
    const required = NOTIONAL * PRINCIPAL / 1_000_000n;
    await usdc.connect(issuer).approve(await bond.getAddress(), required);
    await bond.connect(issuer).reserve(required);

    // 만기 claim
    await time.increaseTo(maturity + 1);
    const before = await usdc.balanceOf(investor.address);
    await bond.connect(investor).claim(0);
    const after  = await usdc.balanceOf(investor.address);

    expect(after - before).to.equal(required);
    expect(await bond.balanceOf(investor.address)).to.equal(0);
  });
});
