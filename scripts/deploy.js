const { ethers } = require("hardhat");

// Sepolia USDC 주소 (Circle 공식)
const SEPOLIA_USDC = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238";

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("배포 계정:", deployer.address);
  console.log("잔액:", ethers.formatEther(await ethers.provider.getBalance(deployer.address)), "ETH");

  // ── BondFactory 배포 ─────────────────────────────────────
  console.log("\n BondFactory 배포 중...");
  const Factory = await ethers.getContractFactory("BondFactory");
  const factory = await Factory.deploy();
  await factory.waitForDeployment();
  const factoryAddress = await factory.getAddress();
  console.log("✅ BondFactory 배포 완료:", factoryAddress);

  // ── USDC 화이트리스트 등록 ───────────────────────────────
  console.log("\n Sepolia USDC 화이트리스트 등록 중...");
  const tx = await factory.setAllowedUSDC(SEPOLIA_USDC, true);
  await tx.wait();
  console.log("✅ USDC 등록 완료:", SEPOLIA_USDC);

  // ── 배포 정보 출력 ───────────────────────────────────────
  console.log("\n========================================");
  console.log("배포 정보 (README에 기록해두세요)");
  console.log("========================================");
  console.log("Network      : Ethereum Sepolia");
  console.log("BondFactory  :", factoryAddress);
  console.log("USDC         :", SEPOLIA_USDC);
  console.log("Deployer     :", deployer.address);
  console.log("Etherscan    :", `https://sepolia.etherscan.io/address/${factoryAddress}`);
  console.log("========================================");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
