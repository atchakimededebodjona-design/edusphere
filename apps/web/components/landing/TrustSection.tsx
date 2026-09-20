import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { FolderIcon, LayersIcon, ShieldIcon, UsersIcon } from "@/components/landing/icons";

// Formulations volontairement sobres — jamais "100% sécurisé", jamais une certification/conformité
// non obtenue. Chaque point décrit un mécanisme réellement implémenté dans le produit.
const TRUST_POINTS = [
  { icon: ShieldIcon, title: "Accès sécurisé", text: "Authentification par compte et gestion des sessions." },
  {
    icon: LayersIcon,
    title: "Séparation des établissements",
    text: "Les données de chaque école restent strictement isolées des autres.",
  },
  {
    icon: UsersIcon,
    title: "Gestion des rôles",
    text: "Chaque utilisateur n'accède qu'aux informations liées à son rôle.",
  },
  {
    icon: FolderIcon,
    title: "Sauvegardes",
    text: "Des sauvegardes régulières protègent les données de l'établissement.",
  },
];

export function TrustSection() {
  return (
    <section className="bg-white py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">
            Une plateforme pensée pour la confiance.
          </h2>
        </ScrollReveal>

        <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {TRUST_POINTS.map((point, i) => {
            const Icon = point.icon;
            return (
              <ScrollReveal key={point.title} delayMs={i * 80}>
                <div className="h-full rounded-2xl border border-slate-200 p-6 text-center">
                  <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-brand-blue/10 text-brand-blue">
                    <Icon className="h-6 w-6" />
                  </span>
                  <h3 className="mt-4 text-sm font-semibold text-brand-text">{point.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{point.text}</p>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
