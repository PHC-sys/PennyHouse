"use client";

import { useReadContracts } from "wagmi";
import Link from "next/link";
import StructuredBondABI from "@/lib/StructuredBondABI.json";
import { fromTimestamp, shortAddr } from "@/lib/utils";

interface Props {
  address: `0x${string}`;
}

export function BondCard({ address }: Props) {
  const contract = { address, abi: StructuredBondABI } as const;

  const { data } = useReadContracts({
    contracts: [
      { ...contract, functionName: "name" },
      { ...contract, functionName: "symbol" },
      { ...contract, functionName: "issuer" },
      { ...contract, functionName: "maxNotional" },
      { ...contract, functionName: "couponRateBps" },
      { ...contract, functionName: "issueDate" },
      { ...contract, functionName: "issuanceComplete" },
      { ...contract, functionName: "totalSupply" },
    ],
  });

  const name             = data?.[0]?.result as string;
  const symbol           = data?.[1]?.result as string;
  const issuer           = data?.[2]?.result as string;
  const maxNotional      = data?.[3]?.result as bigint;
  const couponRateBps    = data?.[4]?.result as bigint;
  const issueDate        = data?.[5]?.result as bigint;
  const issuanceComplete = data?.[6]?.result as boolean;
  const totalSupply      = data?.[7]?.result as bigint;

  if (!name) {
    return (
      <div className="border border-gray-800 rounded-xl p-5 animate-pulse bg-gray-900 h-24" />
    );
  }

  const notionalUSDC = maxNotional ? Number(maxNotional) / 1_000_000 : 0;
  const rate         = couponRateBps ? Number(couponRateBps) / 100 : 0;
  const subscribed   = totalSupply ? Number(totalSupply) / 1_000_000 : 0;
  const fillPct      = maxNotional ? Math.round((subscribed / notionalUSDC) * 100) : 0;

  return (
    <Link href={`/bond/${address}`}>
      <div className="border border-gray-800 hover:border-gray-600 rounded-xl p-5 bg-gray-900 hover:bg-gray-800 transition cursor-pointer">
        <div className="flex items-start justify-between">
          {/* 왼쪽: 채권 정보 */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-white">{name}</span>
              <span className="text-xs text-gray-500 font-mono bg-gray-800 px-2 py-0.5 rounded">
                {symbol}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded ${
                issuanceComplete
                  ? "bg-green-900 text-green-300"
                  : "bg-yellow-900 text-yellow-300"
              }`}>
                {issuanceComplete ? "발행 완료" : "청약 중"}
              </span>
            </div>
            <p className="text-sm text-gray-400">
              발행자: <span className="font-mono">{shortAddr(issuer)}</span>
            </p>
            {issueDate && (
              <p className="text-sm text-gray-400">
                발효일: {fromTimestamp(issueDate)}
              </p>
            )}
          </div>

          {/* 오른쪽: 금리 / Notional */}
          <div className="text-right">
            <p className="text-2xl font-bold text-blue-400">{rate}%</p>
            <p className="text-sm text-gray-400">연 이율</p>
            <p className="text-sm text-gray-300 mt-1">
              {notionalUSDC.toLocaleString()} USDC
            </p>
          </div>
        </div>

        {/* 청약 진행바 */}
        {!issuanceComplete && (
          <div className="mt-4">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>청약 현황</span>
              <span>{subscribed.toLocaleString()} / {notionalUSDC.toLocaleString()} USDC ({fillPct}%)</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div
                className="bg-blue-500 h-1.5 rounded-full"
                style={{ width: `${Math.min(fillPct, 100)}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}
