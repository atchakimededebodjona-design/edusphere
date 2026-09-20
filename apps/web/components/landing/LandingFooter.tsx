import Link from "next/link";
import { BrandSymbol } from "@/components/branding/BrandLogo";

// Aucun lien social : aucun compte social réel n'existe encore pour ce projet — mieux vaut n'en
// afficher aucun que d'inventer une URL, conformément à la consigne.
const COLUMNS = [
  {
    title: "Produit",
    links: [
      { label: "Fonctionnalités", href: "#fonctionnalites" },
      { label: "Portail parent", href: "#solutions" },
      { label: "À venir", href: "#fonctionnalites" },
    ],
  },
  {
    title: "Entreprise",
    links: [
      { label: "À propos", href: "#a-propos" },
      { label: "Contact", href: "#contact" },
    ],
  },
  {
    title: "Support",
    links: [
      { label: "Aide", href: "#contact" },
      { label: "Connexion", href: "/login" },
    ],
  },
];

export function LandingFooter() {
  return (
    <footer className="bg-white">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div className="flex items-center gap-2">
              <BrandSymbol className="h-8 w-8" />
              <span className="text-lg font-bold text-brand-text">EduLinkage</span>
            </div>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-slate-500">
              La plateforme qui connecte les écoles, les enseignants, les parents et les élèves.
            </p>
          </div>

          {COLUMNS.map((column) => (
            <div key={column.title}>
              <h3 className="text-sm font-semibold text-brand-text">{column.title}</h3>
              <ul className="mt-3 space-y-2">
                {column.links.map((link) => (
                  <li key={link.label}>
                    {link.href.startsWith("/") ? (
                      <Link href={link.href} className="text-sm text-slate-500 transition hover:text-brand-blue">
                        {link.label}
                      </Link>
                    ) : (
                      <a href={link.href} className="text-sm text-slate-500 transition hover:text-brand-blue">
                        {link.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-10 border-t border-slate-100 pt-6">
          <p className="text-xs text-slate-400">© 2026 EduLinkage. Tous droits réservés.</p>
        </div>
      </div>
    </footer>
  );
}
