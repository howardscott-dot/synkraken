/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        abyss: "#090a0c",
        panel: "#0f1115",
        panel2: "#141820",
        line: "#29313a",
        cyanop: "#00d9ff",
        amberop: "#ffb300",
        danger: "#ff5252",
        muted: "#8b96a5",
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
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
