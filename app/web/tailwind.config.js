/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // The palette from docs/brand/README.md. Navy anchors, mint is the accent
      // on dark surfaces and teal is its pressed state.
      colors: {
        brand: {
          navy: '#182C3A',
          teal: '#00A88F',
          mint: '#26D6BC',
          paper: '#F3F7F8',
        },
      },
      fontFamily: {
        sans: [
          'Raleway',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
}
