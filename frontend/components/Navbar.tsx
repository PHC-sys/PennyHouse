"use client";

import Link from "next/link";
import { useAccount, useConnect, useDisconnect } from "wagmi";
import { injected } from "wagmi/connectors";
import { shortAddr } from "@/lib/utils";

export function Navbar() {
  const { address, isConnected } = useAccount();
  const { connect } = useConnect();
  const { disconnect } = useDisconnect();

  return (
    <nav className="border-b border-gray-800 px-4 py-4">
      <div className="max-w-5xl mx-auto flex items-center justify-between">
        {/* 로고 */}
        <Link href="/" className="text-xl font-bold text-white">
          PennyHouse
          <span className="ml-2 text-xs text-gray-400 font-normal">Sepolia</span>
        </Link>

        {/* 메뉴 */}
        <div className="flex items-center gap-6">
          <Link href="/" className="text-sm text-gray-400 hover:text-white transition">
            채권 목록
          </Link>
          <Link href="/issue" className="text-sm text-gray-400 hover:text-white transition">
            채권 발행
          </Link>

          {/* 지갑 연결 */}
          {isConnected ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-green-400 font-mono">
                {shortAddr(address!)}
              </span>
              <button
                onClick={() => disconnect()}
                className="text-xs text-gray-500 hover:text-gray-300 transition"
              >
                연결 해제
              </button>
            </div>
          ) : (
            <button
              onClick={() => connect({ connector: injected() })}
              className="bg-blue-600 hover:bg-blue-500 text-white text-sm px-4 py-2 rounded-lg transition"
            >
              MetaMask 연결
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}
