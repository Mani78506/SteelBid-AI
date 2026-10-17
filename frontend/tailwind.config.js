/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(214 18% 88%)",
        input: "hsl(214 18% 84%)",
        ring: "hsl(212 72% 45%)",
        background: "hsl(210 20% 98%)",
        foreground: "hsl(220 26% 14%)",
        primary: { DEFAULT: "hsl(210 70% 38%)", foreground: "hsl(0 0% 100%)", 50: "hsl(210 75% 96%)", 100: "hsl(210 60% 90%)", 600: "hsl(210 70% 38%)", 700: "hsl(210 72% 30%)" },
        secondary: { DEFAULT: "hsl(213 15% 93%)", foreground: "hsl(220 20% 20%)" },
        accent: { DEFAULT: "hsl(174 62% 36%)", foreground: "hsl(0 0% 100%)" },
        muted: { DEFAULT: "hsl(213 14% 95%)", foreground: "hsl(218 12% 45%)" },
        destructive: { DEFAULT: "hsl(0 72% 45%)", foreground: "hsl(0 0% 100%)" },
        success: "hsl(152 60% 33%)",
        warning: "hsl(35 85% 40%)",
        sidebar: { DEFAULT: "hsl(222 24% 12%)", hover: "hsl(222 20% 17%)", border: "hsl(222 18% 20%)", muted: "hsl(220 12% 60%)" },
        card: { DEFAULT: "hsl(0 0% 100%)", foreground: "hsl(220 26% 14%)" },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
      borderRadius: { lg: "0.625rem", md: "0.45rem", sm: "0.3rem" },
      boxShadow: { card: "0 1px 2px 0 rgb(0 0 0 / 0.05), 0 1px 3px 0 rgb(0 0 0 / 0.06)" },
    },
  },
  plugins: [],
};
