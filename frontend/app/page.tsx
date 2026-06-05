"use client";

import { useReadContract } from "wagmi";
import Link from "next/link";
import { CONTRACTS } from "@/lib/config";
import BondFactoryABI from "@/lib/BondFactoryABI.json";
import { BondCard } from "@/components/BondCard";

export default function HomePage() {
  const { data: allBonds, isLoading } = useReadContract({
    address: CONTRACTS.BOND_FACTORY,
    abi: BondFactoryABI,
    functionName: "getAllBonds",
  });

  const bonds = (allBonds as `0x${string}`[]) ?? [];

  return (
    <div>
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold">채권 목록</h1>
          <p className="text-gray-400 mt-1">
            온체인에 발행된 채권 {isLoading ? "..." : bonds.length}개
          </p>
        </div>
        <Link
          href="/issue"
          className="bg-blue-600 hover:bg-blue-500 text-white px-5 py-2.5 rounded-lg transition font-medium"
        >
          + 채권 발행
        </Link>
      </div>

      {/* 채권 목록 */}
      {isLoading ? (
        <div className="text-center text-gray-500 py-20">불러오는 중...</div>
      ) : bonds.length === 0 ? (
        <div className="text-center text-gray-500 py-20">
          <p className="text-lg">발행된 채권이 없습니다.</p>
          <p className="text-sm mt-2">첫 번째 채권을 발행해보세요.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {[...bonds].reverse().map((addr) => (
            <BondCard key={addr} address={addr} />
          ))}
        </div>
      )}
    </div>
  );
}
