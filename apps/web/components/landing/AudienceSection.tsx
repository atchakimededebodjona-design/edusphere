import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { BookOpenIcon, GraduationCapIcon, LayersIcon, UsersIcon } from "@/components/landing/icons";

const AUDIENCES = [
  {
    icon: LayersIcon,
    title: "Directeur",
    text: "Pilotez votre établissement avec une vision claire.",
  },
  {
    icon: BookOpenIcon,
    title: "Enseignant",
    text: "Organisez vos classes, présences, notes et activités.",
  },
  {
    icon: UsersIcon,
    title: "Parent",
    text: "Suivez la scolarité de votre enfant depuis votre espace.",
  },
  {
    icon: GraduationCapIcon,
    title: "Élève",
    text: "Accédez à vos informations scolaires au même endroit.",
  },
];

export function AudienceSection() {
  return (
    <section className="bg-white py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">
            Une seule plateforme pour toute votre communauté scolaire.
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            EduLinkage rapproche les principaux acteurs de l&apos;établissement autour d&apos;une même
            expérience numérique.
          </p>
        </ScrollReveal>

        <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {AUDIENCES.map((audience, i) => {
            const Icon = audience.icon;
            return (
              <ScrollReveal key={audience.title} delayMs={i * 80}>
                <div className="group h-full rounded-2xl border border-slate-200 bg-white p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brand-blue/40 hover:shadow-lg">
                  <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-blue/10 text-brand-blue transition-colors group-hover:bg-brand-blue group-hover:text-white">
                    <Icon className="h-6 w-6" />
                  </span>
                  <h3 className="mt-4 text-lg font-semibold text-brand-text">{audience.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-600">{audience.text}</p>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
