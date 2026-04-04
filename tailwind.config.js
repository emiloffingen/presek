/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Inter', 'Roboto', 'sans-serif'],
      },
      colors: {
        primary: 'var(--bg-primary)',
        secondary: 'var(--bg-secondary)',
        accent: 'var(--accent-color)',
        surface: {
          0: '#ffffff',
          1: '#f7f7f8',
          2: '#f0f0f2',
          3: '#e4e4e8',
        },
        dark: {
          0: '#0f1117',
          1: '#1a1d27',
          2: '#21242f',
          3: '#2a2d3a',
          4: '#363944',
        },
        ink: {
          DEFAULT: '#0f1117',
          soft: '#3d4151',
          muted: '#6b7185',
          faint: '#9ea3b5',
        },
        brand: {
          50:  '#fff0f0',
          100: '#ffe0e0',
          200: '#ffbfbf',
          300: '#ff8585',
          400: '#ff4d4d',
          500: '#e82323',
          600: '#cc1a1a',
          700: '#a81414',
          800: '#8a1212',
          900: '#6b1010',
        },
        blue: {
          50:  '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        amber: {
          50:  '#fffbeb',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
        },
        emerald: {
          500: '#10b981',
          600: '#059669',
        },
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
      },
      boxShadow: {
        'card': '0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.05)',
        'card-hover': '0 4px 12px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.06)',
        'panel': '0 0 0 1px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.06)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.25s ease-out',
      },
      keyframes: {
        fadeIn: {
          'from': { opacity: '0' },
          'to': { opacity: '1' },
        },
        slideUp: {
          'from': { opacity: '0', transform: 'translateY(8px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
