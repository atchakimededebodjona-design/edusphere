import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      // Identité visuelle officielle EduLinkage — palette de marque, purement additive (aucune
      // couleur Tailwind par défaut retirée ni modifiée, tout le reste du projet est inchangé).
      colors: {
        brand: {
          navy: "#0B1224",
          blue: "#1565D8",
          cyan: "#18B6E8",
          bg: "#F5F8FC",
          text: "#172033",
        },
      },
    },
  },
  plugins: [],
};

export default config;
