import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { CheckCircleIcon, ShieldIcon, TrendingUpIcon, UsersIcon } from "@/components/landing/icons";

const PILLARS = [
  {
    icon: UsersIcon,
    title: "Simplicité",
    text: "Une expérience claire pour les équipes scolaires.",
  },
  {
    icon: CheckCircleIcon,
    title: "Accessibilité",
    text: "Une plateforme pensée pour fonctionner sur les appareils utilisés au quotidien.",
  },
  {
    icon: TrendingUpIcon,
    title: "Évolutivité",
    text: "Commencer simplement et faire évoluer l'établissement progressivement.",
  },
  {
    icon: ShieldIcon,
    title: "Sécurité",
    text: "Une architecture conçue pour protéger les données scolaires.",
  },
];

export function AfricaSection() {
  return (
    <section id="a-propos" className="bg-white py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">
            Pensé pour les réalités des écoles africaines.
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            EduLinkage est conçu avec une approche simple, progressive et adaptée aux besoins des
            établissements qui souhaitent entrer dans une nouvelle génération de gestion scolaire.
          </p>
        </ScrollReveal>

        <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((pillar, i) => {
            const Icon = pillar.icon;
            return (
              <ScrollReveal key={pillar.title} delayMs={i * 80}>
                <div className="h-full rounded-2xl border border-slate-200 bg-brand-bg p-6">
                  <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-white text-brand-blue shadow-sm">
                    <Icon className="h-6 w-6" />
                  </span>
                  <h3 className="mt-4 text-lg font-semibold text-brand-text">{pillar.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{pillar.text}</p>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
