"use client";

import { use, useState, useEffect } from "react";
import {
  useReadContracts, useWriteContract,
  useWaitForTransactionReceipt, useAccount,
} from "wagmi";
import StructuredBondABI from "@/lib/StructuredBondABI.json";
import { CONTRACTS } from "@/lib/config";
import { fromTimestamp, fromUSDC, shortAddr, toUSDC } from "@/lib/utils";

// ERC-20 approve ABI (최소)
const ERC20_ABI = [
  {
    name: "approve",
    type: "function",
    inputs: [
      { name: "spender", type: "address" },
      { name: "amount", type: "uint256" },
    ],
    outputs: [{ name: "", type: "bool" }],
    stateMutability: "nonpayable",
  },
] as const;

export default function BondDetailPage({
  params,
}: {
  params: Promise<{ address: string }>;
}) {
  const { address: bondAddress } = use(params);
  const { address: userAddress } = useAccount();
  const [subscribeAmt, setSubscribeAmt] = useState("");
  const [reserveAmt, setReserveAmt] = useState("");

  const bond = { address: bondAddress as `0x${string}`, abi: StructuredBondABI } as const;

  const { data, refetch } = useReadContracts({
    contracts: [
      { ...bond, functionName: "name" },
      { ...bond, functionName: "symbol" },
      { ...bond, functionName: "issuer" },
      { ...bond, functionName: "maxNotional" },
      { ...bond, functionName: "couponRateBps" },
      { ...bond, functionName: "issueDate" },
      { ...bond, functionName: "issuanceComplete" },
      { ...bond, functionName: "totalSubscribed" },
      { ...bond, functionName: "reserveBalance" },
      { ...bond, functionName: "totalSupply" },
      { ...bond, functionName: "getPaymentSchedule" },
      { ...bond, functionName: "accruedInterestPerToken" },
      { ...bond, functionName: "getOpsWallet" },
      { ...bond, functionName: "balanceOf", args: [userAddress ?? "0x0000000000000000000000000000000000000000"] },
    ],
  });

  const name             = data?.[0]?.result as string;
  const symbol           = data?.[1]?.result as string;
  const issuer           = data?.[2]?.result as string;
  const maxNotional      = data?.[3]?.result as bigint;
  const couponRateBps    = data?.[4]?.result as bigint;
  const issueDate        = data?.[5]?.result as bigint;
  const issuanceComplete = data?.[6]?.result as boolean;
  const totalSubscribed  = data?.[7]?.result as bigint;
  const reserveBalance   = data?.[8]?.result as bigint;
  const totalSupply      = data?.[9]?.result as bigint;
  const schedule         = data?.[10]?.result as any[];
  const accruedPerToken  = data?.[11]?.result as bigint;
  const opsWallet        = data?.[12]?.result as string;
  const myBalance        = data?.[13]?.result as bigint;

  // 각 지급 회차별 수령 여부 조회 (schedule 로드 후 동적 생성)
  const { data: claimedData, refetch: refetchClaimed } = useReadContracts({
    contracts: (schedule
      ? schedule.map((_: any, i: number) => ({
          address: bondAddress as `0x${string}`,
          abi: StructuredBondABI as any,
          functionName: "claimed",
          args: [
            userAddress ?? "0x0000000000000000000000000000000000000000",
            BigInt(i),
          ],
        }))
      : []) as any,
  });
  // claimedData[i].result === true 이면 해당 회차 이미 수령
  const claimedStatus: boolean[] = (claimedData ?? []).map(
    (d: any) => d?.result === true
  );

  const { writeContract, data: txHash, isPending } = useWriteContract();
  const { isLoading: isConfirming, isSuccess: txSuccess } = useWaitForTransactionReceipt({
    hash: txHash,
  });

  // 트랜잭션 완료 시 데이터 자동 갱신 → 버튼 상태 즉시 반영
  useEffect(() => {
    if (txSuccess) {
      refetch();
      refetchClaimed();
    }
  }, [txSuccess]);

  const isIssuer = userAddress?.toLowerCase() === issuer?.toLowerCase();
  const now = BigInt(Math.floor(Date.now() / 1000));

  if (!name) {
    return <div className="text-center text-gray-500 py-20">불러오는 중...</div>;
  }

  // USDC Approve → Subscribe
  const handleSubscribe = () => {
    const amount = toUSDC(subscribeAmt);
    writeContract({
      address: CONTRACTS.USDC,
      abi: ERC20_ABI,
      functionName: "approve",
      args: [bondAddress as `0x${string}`, amount],
    });
  };

  // 청약 호출 (approve 후 별도 버튼 or 연속 처리)
  const handleSubscribeConfirm = () => {
    writeContract({
      address: bondAddress as `0x${string}`,
      abi: StructuredBondABI,
      functionName: "subscribe",
      args: [toUSDC(subscribeAmt)],
    });
  };

  // Reserve 적립
  const handleReserve = () => {
    const amount = toUSDC(reserveAmt);
    writeContract({
      address: CONTRACTS.USDC,
      abi: ERC20_ABI,
      functionName: "approve",
      args: [bondAddress as `0x${string}`, amount],
    });
  };

  const handleReserveConfirm = () => {
    writeContract({
      address: bondAddress as `0x${string}`,
      abi: StructuredBondABI,
      functionName: "reserve",
      args: [toUSDC(reserveAmt)],
    });
  };

  // 발행 완료
  const handleCompleteIssuance = () => {
    writeContract({ ...bond, functionName: "completeIssuance", args: [] });
  };

  // 지급 청구
  const handleClaim = (index: number) => {
    writeContract({ ...bond, functionName: "claim", args: [BigInt(index)] });
  };

  const notionalNum      = maxNotional ? Number(maxNotional) / 1_000_000 : 0;
  const subscribedNum    = totalSubscribed ? Number(totalSubscribed) / 1_000_000 : 0;
  const reserveNum       = reserveBalance ? Number(reserveBalance) / 1_000_000 : 0;
  const accruedNum       = accruedPerToken ? Number(accruedPerToken) / 1_000_000 : 0;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* 헤더 */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-3xl font-bold">{name}</h1>
          <span className="text-sm text-gray-500 font-mono bg-gray-800 px-2 py-1 rounded">
            {symbol}
          </span>
          <span className={`text-xs px-2 py-1 rounded ${
            issuanceComplete
              ? "bg-green-900 text-green-300"
              : "bg-yellow-900 text-yellow-300"
          }`}>
            {issuanceComplete ? "발행 완료" : "청약 중"}
          </span>
        </div>
        <p className="text-sm text-gray-400">
          발행자: <span className="font-mono">{issuer ? shortAddr(issuer) : "-"}</span>
          {" · "}발효일: {issueDate ? fromTimestamp(issueDate) : "-"}
          {" · "}연 {couponRateBps ? Number(couponRateBps) / 100 : 0}%
          {schedule && schedule.length > 0 && issueDate && (() => {
            const maturity = BigInt(schedule[schedule.length - 1].date);
            const years = Number(maturity - issueDate) / (365 * 24 * 60 * 60);
            return <>{" · "}만기 {years.toFixed(2)}년</>;
          })()}
        </p>
      </div>

      {/* 채권 현황 */}
      <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 grid grid-cols-2 gap-4">
        <div>
          <p className="text-sm text-gray-400 mb-1">총 발행액</p>
          <p className="text-2xl font-bold text-white">{notionalNum.toLocaleString()} <span className="text-sm text-gray-400">USDC</span></p>
        </div>
        <div>
          <p className="text-sm text-gray-400 mb-1">청약 현황</p>
          <p className="text-2xl font-bold text-white">{subscribedNum.toLocaleString()} <span className="text-sm text-gray-400">USDC</span></p>
          <div className="w-full bg-gray-700 rounded-full h-1.5 mt-1">
            <div
              className="bg-blue-500 h-1.5 rounded-full"
              style={{ width: `${Math.min((subscribedNum / notionalNum) * 100, 100)}%` }}
            />
          </div>
        </div>
        <div>
          <p className="text-sm text-gray-400 mb-1">Reserve 잔액</p>
          <p className="text-2xl font-bold text-white">{reserveNum.toLocaleString()} <span className="text-sm text-gray-400">USDC</span></p>
        </div>
        <div>
          <p className="text-sm text-gray-400 mb-1">경과이자 (토큰 1개당)</p>
          <p className="text-2xl font-bold text-blue-400">{accruedNum.toFixed(6)} <span className="text-sm text-gray-400">USDC</span></p>
          <p className="text-xs text-gray-500 mt-0.5">Act/360 기준</p>
        </div>
      </section>

      {/* 운용 지갑 (공개 시) */}
      {opsWallet && opsWallet !== "0x0000000000000000000000000000000000000000" && (
        <section className="bg-red-950 border border-red-800 rounded-xl p-4">
          <p className="text-sm text-red-300 font-semibold mb-1">⚠️ Reserve 부족 — 운용 지갑 공개됨</p>
          <p className="font-mono text-sm text-red-200">{opsWallet}</p>
          <div className="flex gap-3 mt-2">
            <a
              href={`https://debank.com/profile/${opsWallet}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:underline"
            >
              Debank에서 보기 ↗
            </a>
            <a
              href={`https://sepolia.etherscan.io/address/${opsWallet}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:underline"
            >
              Etherscan에서 보기 ↗
            </a>
          </div>
        </section>
      )}

      {/* 캐시플로우 차트 */}
      {schedule && schedule.length > 0 && (() => {
        const amounts = schedule.map((p: any) => Number(p.amountPerToken) / 1_000_000);
        const maxAmt = Math.max(...amounts);
        const chartH = 140;
        const yTicks = [0, maxAmt * 0.5, maxAmt];
        return (
          <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="font-semibold mb-4">캐시플로우</h2>
            <div className="flex gap-2">
              {/* y축 */}
              <div className="flex flex-col justify-between items-end pb-8" style={{ height: `${chartH + 8}px` }}>
                {yTicks.slice().reverse().map((t, i) => (
                  <span key={i} className="text-xs text-gray-600 tabular-nums">{t.toFixed(2)}</span>
                ))}
              </div>
              {/* 차트 영역 */}
              <div className="flex-1">
                {/* 그리드 + 바 */}
                <div className="relative" style={{ height: `${chartH}px` }}>
                  {/* 수평 그리드 라인 */}
                  {[0, 0.5, 1].map((ratio, i) => (
                    <div
                      key={i}
                      className="absolute w-full border-t border-gray-800"
                      style={{ bottom: `${ratio * 100}%` }}
                    />
                  ))}
                  {/* 바들 */}
                  <div className="absolute inset-0 flex items-end justify-around px-4">
                    {schedule.map((p: any, i: number) => {
                      const amt = Number(p.amountPerToken) / 1_000_000;
                      const barH = Math.max((amt / maxAmt) * chartH, 3);
                      const principalAmt = 1.0;
                      const couponAmt = amt - principalAmt;
                      const principalH = (principalAmt / maxAmt) * chartH;
                      const couponH = Math.max((couponAmt / maxAmt) * chartH, 2);
                      return (
                        <div key={i} className="flex flex-col items-center gap-1" style={{ width: "40px" }}>
                          <span className="text-xs text-gray-400 tabular-nums">{amt.toFixed(4)}</span>
                          {p.isPrincipal ? (
                            <div style={{ width: "28px", height: `${barH}px` }} className="flex flex-col justify-end">
                              <div style={{ height: `${couponH}px` }} className="bg-blue-500 rounded-t" />
                              <div style={{ height: `${principalH}px` }} className="bg-orange-500" />
                            </div>
                          ) : (
                            <div
                              style={{ height: `${barH}px`, width: "28px" }}
                              className="bg-blue-500 rounded-t"
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
                {/* x축 라벨 */}
                <div className="flex justify-around px-4 mt-2">
                  {schedule.map((p: any, i: number) => (
                    <div key={i} className="flex flex-col items-center" style={{ width: "40px" }}>
                      <span className="text-xs text-gray-500">{fromTimestamp(BigInt(p.date)).replace("2026. ", "")}</span>
                      <span className={`text-xs ${p.isPrincipal ? "text-orange-400" : "text-blue-400"}`}>
                        {p.isPrincipal ? "원금" : "쿠폰"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 투자자 예상 수령액 */}
            {myBalance != null && myBalance > 0n && schedule && (() => {
              const tokenAmt = Number(myBalance) / 1_000_000;
              const total = schedule.reduce((sum: number, p: any) => {
                return sum + (Number(p.amountPerToken) / 1_000_000) * tokenAmt;
              }, 0);
              return (
                <div className="mt-4 pt-4 border-t border-gray-800 flex items-center justify-between">
                  <span className="text-sm text-gray-400">
                    내 보유 <span className="text-white font-mono">{tokenAmt.toFixed(0)} {symbol}</span> 기준 만기까지 총 예상 수령액
                  </span>
                  <span className="text-lg font-bold text-green-400">{total.toFixed(6)} USDC</span>
                </div>
              );
            })()}
          </section>
        );
      })()}

      {/* 지급 스케줄 */}
      {schedule && schedule.length > 0 && (() => {
        // 내가 수령 가능한 미수령 회차 수 (토큰 보유자에게만 의미 있음)
        const claimableCount = myBalance && myBalance > 0n
          ? schedule.filter((p: any, i: number) => {
              return now >= BigInt(p.date) && !claimedStatus[i];
            }).length
          : 0;

        return (
          <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold">지급 스케줄</h2>
              {/* 일괄 수령 버튼: 미수령 도래 회차가 2개 이상일 때만 표시 */}
              {claimableCount >= 2 && (
                <button
                  onClick={() => writeContract({ ...bond, functionName: "claimAll", args: [] })}
                  disabled={isPending || isConfirming}
                  className="text-xs bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white px-3 py-1.5 rounded transition"
                >
                  일괄 수령 ({claimableCount}건)
                </button>
              )}
            </div>
            <div className="space-y-3">
              {schedule.map((p: any, i: number) => {
                const payDate = BigInt(p.date);
                const isDue = now >= payDate;
                const isClaimed = claimedStatus[i] ?? false;
                const amount = Number(p.amountPerToken) / 1_000_000;

                return (
                  <div key={i} className="flex items-center justify-between p-3 bg-gray-800 rounded-lg">
                    <div>
                      <span className={`text-xs px-2 py-0.5 rounded mr-2 ${
                        p.isPrincipal
                          ? "bg-orange-900 text-orange-300"
                          : "bg-blue-900 text-blue-300"
                      }`}>
                        {p.isPrincipal ? "원금+쿠폰" : "쿠폰"}
                      </span>
                      <span className="text-sm">{fromTimestamp(payDate)}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-gray-300">
                        {amount.toFixed(6)} USDC/토큰
                      </span>
                      {issuanceComplete && isDue && isClaimed && (
                        <span className="text-xs text-gray-500 px-3 py-1">✓ 수령 완료</span>
                      )}
                      {issuanceComplete && isDue && !isClaimed && (
                        <button
                          onClick={() => handleClaim(i)}
                          disabled={isPending || isConfirming}
                          className="text-xs bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white px-3 py-1 rounded transition"
                        >
                          수령
                        </button>
                      )}
                      {!isDue && (
                        <span className="text-xs text-gray-500">미도래</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })()}

      {/* 청약 (발행 전) */}
      {!issuanceComplete && (
        <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-3">
          <h2 className="font-semibold">청약하기</h2>
          <div className="flex gap-3">
            <input
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500"
              type="number"
              placeholder="청약 금액 (USDC)"
              value={subscribeAmt}
              onChange={(e) => setSubscribeAmt(e.target.value)}
            />
            <button
              onClick={handleSubscribe}
              disabled={isPending || isConfirming || !subscribeAmt}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition"
            >
              1. USDC 승인
            </button>
            <button
              onClick={handleSubscribeConfirm}
              disabled={isPending || isConfirming || !subscribeAmt}
              className="bg-green-700 hover:bg-green-600 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition"
            >
              2. 청약
            </button>
          </div>
          <p className="text-xs text-gray-500">
            USDC 승인 후 청약 버튼을 누르세요. PAR 가격(1 USDC = 채권 토큰 1개)으로 청약됩니다.
          </p>
        </section>
      )}

      {/* 발행자 전용 패널 */}
      {isIssuer && (
        <section className="bg-gray-900 border border-yellow-800 rounded-xl p-6 space-y-4">
          <h2 className="font-semibold text-yellow-300">발행자 전용</h2>

          {/* 발행 완료: 발효일 경과 OR 완판 시 */}
          {!issuanceComplete && (now >= (issueDate ?? 0n) || (totalSubscribed ?? 0n) >= (maxNotional ?? 1n)) && (
            <div>
              <p className="text-sm text-gray-400 mb-2">
                {(totalSubscribed ?? 0n) >= (maxNotional ?? 1n)
                  ? "완판됐습니다. 지금 발행 완료할 수 있습니다."
                  : "발효일이 지났습니다. 발행을 완료하면 청약 대금이 내 지갑으로 전송됩니다."}
              </p>
              <button
                onClick={handleCompleteIssuance}
                disabled={isPending || isConfirming}
                className="bg-yellow-600 hover:bg-yellow-500 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition"
              >
                발행 완료 처리
              </button>
            </div>
          )}

          {/* 잉여 Reserve 회수 */}
          {issuanceComplete && (reserveBalance ?? 0n) > 0n && (
            <div>
              <p className="text-sm text-gray-400 mb-2">잉여 Reserve 회수</p>
              <p className="text-xs text-gray-500 mb-2">
                다음 미도래 지급에 필요한 금액을 초과하는 Reserve를 회수합니다.
              </p>
              <button
                onClick={() => writeContract({ ...bond, functionName: "withdrawExcessReserve", args: [] })}
                disabled={isPending || isConfirming}
                className="bg-gray-600 hover:bg-gray-500 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition"
              >
                잉여 Reserve 회수
              </button>
            </div>
          )}

          {/* Reserve 적립 */}
          <div>
            <p className="text-sm text-gray-400 mb-2">Reserve 적립</p>
            <div className="flex gap-3">
              <input
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-yellow-500"
                type="number"
                placeholder="적립 금액 (USDC)"
                value={reserveAmt}
                onChange={(e) => setReserveAmt(e.target.value)}
              />
              <button
                onClick={handleReserve}
                disabled={isPending || isConfirming || !reserveAmt}
                className="bg-yellow-700 hover:bg-yellow-600 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition"
              >
                1. USDC 승인
              </button>
              <button
                onClick={handleReserveConfirm}
                disabled={isPending || isConfirming || !reserveAmt}
                className="bg-yellow-600 hover:bg-yellow-500 disabled:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm transition"
              >
                2. 적립
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Etherscan 링크 */}
      <div className="text-center">
        <a
          href={`https://sepolia.etherscan.io/address/${bondAddress}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-gray-500 hover:text-gray-300 transition"
        >
          Etherscan에서 보기 ↗
        </a>
      </div>
    </div>
  );
}
