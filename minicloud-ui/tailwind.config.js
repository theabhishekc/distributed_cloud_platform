/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'terminal-bg': '#0a0a0f',
        'terminal-surface': '#0d0d1a',
        'terminal-border': '#1a1a2e',
        'terminal-cyan': '#00d4ff',
        'terminal-amber': '#f59e0b',
        'terminal-red': '#ef4444',
        'terminal-green': '#22c55e',
        'terminal-dim': '#4a4a6a',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '2px',
        sm: '2px',
        md: '4px',
        lg: '4px',
        full: '9999px',
      },
    },
  },
  plugins: [],
}
