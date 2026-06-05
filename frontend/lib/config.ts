import { http, createConfig } from "wagmi";
import { sepolia } from "wagmi/chains";
import { injected } from "wagmi/connectors";

// 배포된 컨트랙트 주소
export const CONTRACTS = {
  BOND_FACTORY: "0x5baa53e4e74Bb5E51556425101a5183a9b675776" as `0x${string}`,
  USDC:         "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238" as `0x${string}`,
};

// wagmi 설정
export const config = createConfig({
  chains: [sepolia],
  connectors: [injected()],
  transports: {
    [sepolia.id]: http("https://ethereum-sepolia-rpc.publicnode.com"),
  },
});
