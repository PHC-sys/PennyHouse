const { ethers } = require("hardhat");

const FACTORY_ADDRESS = "0xbAc2F972EFc5a29033B48476BeAF24841464cdF3";
const SEPOLIA_USDC    = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238";

async function main() {
  const factory = await ethers.getContractAt("BondFactory", FACTORY_ADDRESS);

  const allowed = await factory.allowedUSDC(SEPOLIA_USDC);
  console.log("확인한 USDC 주소  :", SEPOLIA_USDC);
  console.log("화이트리스트 등록  :", allowed);
  console.log("총 채권 수        :", (await factory.totalBonds()).toString());
  console.log("Owner             :", await factory.owner());
}

main().catch(console.error);
