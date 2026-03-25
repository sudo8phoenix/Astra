/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Design System Colors
        primary: {
          DEFAULT: '#6C63FF',
          light: '#8B7FFF',
          dark: '#4C43DF',
        },
        secondary: {
          DEFAULT: '#00D4FF',
          light: '#4DDEFF',
          dark: '#00A8CC',
        },
        background: {
          DEFAULT: '#0F172A',
          card: 'rgba(255, 255, 255, 0.05)',
        },
        text: {
          primary: '#FFFFFF',
          secondary: '#94A3B8',
          tertiary: '#64748B',
        },
      },
      gradients: {
        'primary-gradient': 'linear-gradient(135deg, #6C63FF, #00D4FF)',
        'glow-effect': 'radial-gradient(circle, rgba(0, 212, 255, 0.4), transparent)',
      },
      spacing: {
        'card': '16px',
        'card-lg': '24px',
      },
      borderRadius: {
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
        'xl': '24px',
      },
      fontSize: {
        'h1': '28px',
        'h2': '20px',
        'body': '14px',
      },
      fontFamily: {
        'display': ['Inter', 'SF Pro Display', 'system-ui', 'sans-serif'],
        'sans': ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'glow': '0 0 20px rgba(0, 212, 255, 0.2)',
        'glow-lg': '0 0 40px rgba(108, 99, 255, 0.3)',
      },
      animation: {
        'typing': 'typing 0.7s steps(4, end) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'scale-pop': 'scalePop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'pulse': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        typing: {
          '0%': { width: '0px' },
          '100%': { width: '16px' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scalePop: {
          '0%': { transform: 'scale(0.8)', opacity: '0' },
          '50%': { transform: 'scale(1.05)' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
      },
      screens: {
        'sm': '640px',
        'md': '768px',
        'lg': '1024px',
        'xl': '1280px',
        '2xl': '1536px',
      },
    },
  },
  plugins: [],
}
