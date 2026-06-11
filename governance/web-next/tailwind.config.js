/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,jsx}', './components/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg:      '#0a0e14',
        surface: '#111722',
        card:    '#151c28',
        border:  '#1f2937',
        muted:   '#7d8a9c',
        fg:      '#e7edf5',
        brand:   '#5b8def',
        'brand-dim': '#2f4a7a',
        long:    '#26d07c',
        short:   '#f6465d',
        warn:    '#f0b90b',
      },
      fontFamily: {
        sans: ['Pretendard', 'Malgun Gothic', 'Segoe UI', 'sans-serif'],
        mono: ['SF Mono', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(91,141,239,0.15), 0 8px 30px rgba(0,0,0,0.4)',
        card: '0 1px 3px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.2)',
      },
      borderRadius: { xl: '14px', '2xl': '18px' },
    },
  },
  plugins: [],
};
