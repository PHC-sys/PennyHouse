'use client';
import { useState } from 'react';
import { api } from '@/components/api';
import AssetPicker from '@/components/AssetPicker';

const PROFILES = [
  { v: 'aggressive', label: '공격적 (5x)' },
  { v: 'conservative', label: '보수적 (2x)' },
  { v: 'spot', label: '현물 (1x)' },
];

export default function CreateFundModal({ me, onClose, onCreated }) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState('demo');
  const [visibility, setVisibility] = useState('public');
  const [profile, setProfile] = useState('aggressive');
  const [deposit, setDeposit] = useState(100000);
  const [maxDeposit, setMaxDeposit] = useState('');
  const [universe, setUniverse] = useState(['BTC', 'ETH', 'SOL', 'HYPE']);
  const [allow, setAllow] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  function addAsset(a) {
    setUniverse((u) => u.includes(a.symbol) ? u : [...u, a.symbol]);
  }
  function addMany(list) {
    setUniverse((u) => {
      const set = new Set(u);
      list.forEach((a) => set.add(a.symbol));
      return [...set];
    });
  }
  function removeAsset(s) { setUniverse((u) => u.filter((x) => x !== s)); }

  async function submit() {
    if (!name.trim()) { setErr('펀드 이름을 입력하세요'); return; }
    if (universe.length === 0) { setErr('운용 자산을 1개 이상 선택'); return; }
    setBusy(true); setErr('');
    try {
      const body = {
        name: name.trim(), kind, visibility, creator: me, profile,
        initial_deposit: +deposit,
        max_deposit: maxDeposit ? +maxDeposit : null,
        universe,
        allowlist: visibility === 'private'
          ? allow.split(',').map((s) => s.trim()).filter(Boolean) : [],
      };
      const f = await api('/api/funds', { method: 'POST', body: JSON.stringify(body) });
      onCreated(f);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}>
      <div className="bg-surface border border-border rounded-2xl shadow-glow w-full max-w-[560px]
        max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-border flex items-center">
          <h3 className="font-bold">➕ 펀드 개설</h3>
          <button className="ml-auto btn-ghost py-1" onClick={onClose}>닫기 ✕</button>
        </div>
        <div className="p-5 space-y-4">
          <Field label="펀드 이름">
            <input className="input w-full" value={name} onChange={(e) => setName(e.target.value)}
              placeholder="예: 우리끼리 펀드" /></Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="종류">
              <div className="flex gap-1.5">
                <Chip on={kind === 'demo'} onClick={() => setKind('demo')}>Demo</Chip>
                <Chip on={kind === 'real'} onClick={() => setKind('real')}>실제</Chip>
              </div></Field>
            <Field label="공개 범위">
              <div className="flex gap-1.5">
                <Chip on={visibility === 'public'} onClick={() => setVisibility('public')}>Public</Chip>
                <Chip on={visibility === 'private'} onClick={() => setVisibility('private')}>Private</Chip>
              </div></Field>
          </div>

          {visibility === 'private' && (
            <Field label="허용 지갑 주소 (쉼표 구분 · 인증은 추후)">
              <input className="input w-full" value={allow} onChange={(e) => setAllow(e.target.value)}
                placeholder="0xABC, 0xDEF" /></Field>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="펀드 프로파일">
              <select className="input w-full" value={profile} onChange={(e) => setProfile(e.target.value)}>
                {PROFILES.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
              </select></Field>
            <Field label="가상 예치금 ($)">
              <input className="input w-full" type="number" step="10000"
                value={deposit} onChange={(e) => setDeposit(e.target.value)} /></Field>
          </div>

          <Field label="최대 예치금 한도 ($, 선택)">
            <input className="input w-full" type="number" step="10000" value={maxDeposit}
              onChange={(e) => setMaxDeposit(e.target.value)} placeholder="비우면 무제한" /></Field>

          <Field label={`운용 자산 (${universe.length}종)`}>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {universe.map((s) => (
                <span key={s} className="chip chip-active flex items-center gap-1"
                  onClick={() => removeAsset(s)}>
                  {s.split(':').pop()} <span className="text-[10px]">✕</span></span>
              ))}
              <button className="chip" onClick={() => setPickerOpen(true)}>+ 자산 추가</button>
            </div>
          </Field>

          {err && <div className="text-short text-sm">⚠ {err}</div>}
          <button className="btn-primary w-full" onClick={submit} disabled={busy}>
            {busy ? '개설 중…' : '펀드 개설하기'}</button>
        </div>
      </div>
      <AssetPicker open={pickerOpen} onClose={() => setPickerOpen(false)}
        onSelect={addAsset} onAddAll={addMany} title="운용 자산 추가" />
    </div>
  );
}

function Field({ label, children }) {
  return <div><div className="label">{label}</div>{children}</div>;
}
function Chip({ on, onClick, children }) {
  return <span className={`chip ${on ? 'chip-active' : ''}`} onClick={onClick}>{children}</span>;
}
