/** @type {import('tailwindcss').Config} */
// Codex design tokens — kept in sync with apps/sentinel-ui/tailwind.config.js
// so the public landing page reads as the same world as the game.
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        void: '#0d0d0f',
        parchment: '#111318',
        codex: '#16191f',
        border: '#2a2d35',
        ink: '#e8e4d9',
        dust: '#8a8578',
        amber: '#c9973a',
        leyline: '#4a8c6f',
        blood: '#8c3a3a',
        ether: '#3a6a8c',
      },
      fontFamily: {
        crimson: ['Crimson Pro', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
        cinzel: ['Cinzel', 'serif'],
      },
      animation: {
        'fade-in': 'fadeIn 600ms ease-out',
        'slide-up': 'slideUp 200ms ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
