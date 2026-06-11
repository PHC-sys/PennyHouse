/** @type {import('next').NextConfig} */
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8099';

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // /api/* 요청을 FastAPI 백엔드로 프록시
    return [{ source: '/api/:path*', destination: `${BACKEND}/api/:path*` }];
  },
};

module.exports = nextConfig;
