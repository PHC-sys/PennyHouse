import './globals.css';
import TopNav from '@/components/TopNav';

export const metadata = {
  title: 'GovernanceFund — 백테스트 & 페이퍼 트레이딩',
  description: '투표로 운용하는 사모 거버넌스 펀드. 돈 없이 메커니즘을 체험하세요.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css"
        />
      </head>
      <body className="font-sans antialiased min-h-screen">
        <TopNav />
        <main className="max-w-[1400px] mx-auto px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
