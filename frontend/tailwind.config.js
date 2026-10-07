/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ground: "#EEF2EF", ink: "#0F1F1A", panel: "#FFFFFF", rule: "#CBD6D0", muted: "#4A5D55",
        brand: { DEFAULT: "#0B5D4E", dark: "#073F35", tint: "#DCEDE7" },
        signal: { DEFAULT: "#B8322A", tint: "#F8E3E0" },
        amber: { DEFAULT: "#8A5A00", tint: "#F8EBCF" },
        okay: { DEFAULT: "#23704A", tint: "#DDF0E5" },
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "system-ui", "sans-serif"],
        sans: ['"Instrument Sans"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
