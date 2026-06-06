/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        abyss: "#f5f5f7",
        panel: "rgba(255,255,255,0.72)",
        panel2: "rgba(255,255,255,0.92)",
        line: "rgba(0,0,0,0.08)",
        cyanop: "#007aff",
        amberop: "#b26a00",
        danger: "#d70015",
        muted: "#6e6e73",
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
