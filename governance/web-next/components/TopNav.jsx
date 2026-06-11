'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const TABS = [
  { href: '/', label: '과거 백테스트', icon: '📈' },
  { href: '/paper', label: '라이브 페이퍼 트레이딩', icon: '🗳️' },
  { href: '/market', label: '마켓', icon: '🌐' },
];

export default function TopNav() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-20 backdrop-blur-md bg-bg/80 border-b border-border">
      <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-6">
        <div className="flex items-center gap-2.5">
          <span className="text-xl">🏛️</span>
          <div className="leading-tight">
            <div className="font-bold text-[15px]">GovernanceFund</div>
            <div className="text-[11px] text-muted">백테스트 & 페이퍼 트레이딩</div>
          </div>
        </div>
        <nav className="flex gap-1.5 ml-2">
          {TABS.map((t) => {
            const active = path === t.href;
            return (
              <Link key={t.href} href={t.href}
                className={`btn ${active ? 'bg-card text-brand border border-brand/40'
                  : 'text-muted hover:text-fg'}`}>
                <span className="mr-1.5">{t.icon}</span>{t.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto text-[11px] text-muted hidden md:block">
          Hyperliquid Perp · 실시간
        </div>
      </div>
    </header>
  );
}
