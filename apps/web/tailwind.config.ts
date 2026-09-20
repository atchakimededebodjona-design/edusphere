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
      // Landing page publique — flottement très lent et discret pour les cartes illustratives du
      // Hero/Aperçu produit. Amplitude volontairement faible (8px), jamais utilisée pour un
      // contenu permanent en dehors de ces compositions décoratives ; toujours neutralisée par
      // `motion-reduce:animate-none` côté composant pour respecter prefers-reduced-motion.
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-8px)" },
        },
        // Entrée du Hero au chargement de la page (jouée une seule fois, jamais en boucle) —
        // distincte de `float` (boucle infinie, décorative) et de ScrollReveal (déclenchée au
        // scroll pour les sections suivantes).
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(24px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        float: "float 6s ease-in-out infinite",
        "fade-in": "fade-in 0.6s ease-out both",
        "slide-up": "slide-up 0.7s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
