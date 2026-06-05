/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        abyss: "#0b0b0d",
        panel: "#111113",
        panel2: "#1c1c1e",
        line: "rgba(255,255,255,0.08)",
        cyanop: "#2997ff",
        amberop: "#f5a623",
        danger: "#ff453a",
        muted: "#a1a1a6",
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
        sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Display", "Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
