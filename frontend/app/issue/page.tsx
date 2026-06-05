"use client";

import { useState, useEffect } from "react";
import { useAccount, useWriteContract, useWaitForTransactionReceipt } from "wagmi";
import { useRouter } from "next/navigation";
import { CONTRACTS } from "@/lib/config";
import BondFactoryABI from "@/lib/BondFactoryABI.json";
import {
  toUSDC, toBps, toTimestamp,
  calcCouponPerToken, calcFinalPerToken,
} from "@/lib/utils";

interface PaymentRow {
  date: string;
  isPrincipal: boolean;
}

export default function IssuePage() {
  const { isConnected } = useAccount();
  const router = useRouter();

  // 기본 폼
  const [name, setName]           = useState("");
  const [symbol, setSymbol]       = useState("");
  const [opsWallet, setOpsWallet] = useState("");
  const [notional, setNotional]   = useState("");
  const [rate, setRate]           = useState("");
  const [subStart, setSubStart]   = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [bufferDays, setBufferDays] = useState("7");

  // 지급 스케줄
  const [payments, setPayments] = useState<PaymentRow[]>([
    { date: "", isPrincipal: false },
    { date: "", isPrincipal: true },
  ]);

  const { writeContract, data: txHash, isPending } = useWriteContract();
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({
    hash: txHash,
  });

  const addPayment = () => {
    // 마지막 행 앞에 새 쿠폰 행 추가
    setPayments((prev) => {
      const last = prev[prev.length - 1];
      return [...prev.slice(0, -1), { date: "", isPrincipal: false }, last];
    });
  };

  const removePayment = (i: number) => {
    if (payments.length <= 1) return;
    setPayments((prev) => prev.filter((_, idx) => idx !== i));
  };

  const updatePayment = (i: number, field: keyof PaymentRow, value: string | boolean) => {
    setPayments((prev) =>
      prev.map((p, idx) => (idx === i ? { ...p, [field]: value } : p))
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isConnected) return alert("MetaMask를 먼저 연결해주세요.");

    const couponBps = toBps(rate);

    // 같은 날짜면 발효일에 1초 추가 (컨트랙트: subscriptionStart < issueDate)
    const subStartTs  = BigInt(toTimestamp(subStart));
    const issueDateTs = subStart === issueDate
      ? subStartTs + 1n
      : BigInt(toTimestamp(issueDate));

    // 지급 스케줄 계산
    const paymentDates = payments.map((p) => BigInt(toTimestamp(p.date)));
    const amountsPerToken = payments.map((p, i) => {
      const prevDate = i === 0 ? issueDate : payments[i - 1].date;
      return p.isPrincipal
        ? BigInt(calcFinalPerToken(couponBps, prevDate, p.date))
        : BigInt(calcCouponPerToken(couponBps, prevDate, p.date));
    });
    const isPrincipalArr = payments.map((p) => p.isPrincipal);

    writeContract({
      address: CONTRACTS.BOND_FACTORY,
      abi: BondFactoryABI,
      functionName: "createBond",
      args: [
        CONTRACTS.USDC,
        {
          name,
          symbol,
          opsWallet: opsWallet as `0x${string}`,
          maxNotional: toUSDC(notional),
          couponRateBps: BigInt(couponBps),
          subscriptionStart: subStartTs,
          issueDate: issueDateTs,
          reserveBufferDays: BigInt(bufferDays),
          paymentDates,
          amountsPerToken,
          isPrincipal: isPrincipalArr,
        },
      ],
    });
  };

  useEffect(() => {
    if (isSuccess) router.push("/");
  }, [isSuccess]);

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">채권 발행</h1>
      <p className="text-gray-400 mb-8">채권 조건을 입력하면 스마트 컨트랙트가 자동으로 배포됩니다.</p>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* 기본 정보 */}
        <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          <h2 className="font-semibold text-lg">기본 정보</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-gray-400 mb-1 block">채권 이름</label>
              <input
                className="input"
                placeholder="PENNY-BOND-2026-001"
                value={name} onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-1 block">심볼</label>
              <input
                className="input"
                placeholder="PB2601"
                value={symbol} onChange={(e) => setSymbol(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className="text-sm text-gray-400 mb-1 block">운용 지갑 주소</label>
            <input
              className="input font-mono"
              placeholder="0x..."
              value={opsWallet} onChange={(e) => setOpsWallet(e.target.value)}
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              Reserve 부족 시 이 주소가 공개됩니다.
            </p>
          </div>
        </section>

        {/* 채권 조건 */}
        <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          <h2 className="font-semibold text-lg">채권 조건</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-gray-400 mb-1 block">총 발행액 (USDC)</label>
              <input
                className="input"
                type="number" placeholder="10000"
                value={notional} onChange={(e) => setNotional(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-1 block">연 이율 (%)</label>
              <input
                className="input"
                type="number" step="0.01" placeholder="10"
                value={rate} onChange={(e) => setRate(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-gray-400 mb-1 block">청약 시작일</label>
              <input
                className="input"
                type="date"
                value={subStart} onChange={(e) => setSubStart(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-sm text-gray-400 mb-1 block">발효일 (이자 기산)</label>
              <input
                className="input"
                type="date"
                value={issueDate} onChange={(e) => setIssueDate(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="w-1/2">
            <label className="text-sm text-gray-400 mb-1 block">Reserve 체크 버퍼 (일)</label>
            <input
              className="input"
              type="number" placeholder="7"
              value={bufferDays} onChange={(e) => setBufferDays(e.target.value)}
              required
            />
            <p className="text-xs text-gray-500 mt-1">각 지급일 N일 전에 Reserve를 확인합니다.</p>
          </div>
        </section>

        {/* 지급 스케줄 */}
        <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-lg">지급 스케줄</h2>
            <button
              type="button"
              onClick={addPayment}
              className="text-sm text-blue-400 hover:text-blue-300 transition"
            >
              + 지급일 추가
            </button>
          </div>
          <p className="text-xs text-gray-500">
            마지막 항목은 원금 상환일입니다. 중간 항목은 쿠폰 지급일입니다.
          </p>

          <div className="space-y-3">
            {payments.map((p, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="flex-1">
                  <input
                    className="input"
                    type="date"
                    value={p.date}
                    onChange={(e) => updatePayment(i, "date", e.target.value)}
                    required
                  />
                </div>
                <div className={`text-xs px-3 py-2 rounded-lg font-medium min-w-[80px] text-center ${
                  p.isPrincipal
                    ? "bg-orange-900 text-orange-300"
                    : "bg-blue-900 text-blue-300"
                }`}>
                  {p.isPrincipal ? "원금+쿠폰" : "쿠폰"}
                </div>
                {!p.isPrincipal && (
                  <button
                    type="button"
                    onClick={() => removePayment(i)}
                    className="text-gray-600 hover:text-red-400 transition text-lg"
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* 제출 */}
        <button
          type="submit"
          disabled={isPending || isConfirming}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white py-3 rounded-xl font-semibold transition"
        >
          {isPending ? "MetaMask 서명 대기 중..." :
           isConfirming ? "트랜잭션 처리 중..." :
           "채권 발행하기"}
        </button>
      </form>

      <style jsx>{`
        .input {
          width: 100%;
          background: #111827;
          border: 1px solid #374151;
          border-radius: 0.5rem;
          padding: 0.5rem 0.75rem;
          color: white;
          font-size: 0.875rem;
          outline: none;
          color-scheme: dark;
        }
        .input:focus {
          border-color: #3b82f6;
        }
        .input::-webkit-calendar-picker-indicator {
          filter: invert(1);
          opacity: 0.7;
          cursor: pointer;
        }
      `}</style>
    </div>
  );
}
