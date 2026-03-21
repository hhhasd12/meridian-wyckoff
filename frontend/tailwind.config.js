/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        panel: {
          bg: "#0d1117",
          surface: "#161b22",
          border: "#30363d",
          hover: "#1c2128",
        },
        accent: {
          green: "#3fb950",
          red: "#f85149",
          yellow: "#d29922",
          blue: "#58a6ff",
          purple: "#bc8cff",
          cyan: "#39d2c0",
        },
        text: {
          primary: "#e6edf3",
          secondary: "#8b949e",
          muted: "#484f58",
        },
      },
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Consolas",
          "Monaco",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
