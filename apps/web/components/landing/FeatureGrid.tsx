import { ScrollReveal } from "@/components/landing/ScrollReveal";
import {
  BellIcon,
  BookOpenIcon,
  CalendarIcon,
  ChartBarIcon,
  CheckCircleIcon,
  ClipboardCheckIcon,
  CreditCardIcon,
  FolderIcon,
  GraduationCapIcon,
  LayersIcon,
  MessageSquareIcon,
  ShieldIcon,
  TrendingUpIcon,
  UsersIcon,
} from "@/components/landing/icons";

// Chaque fonctionnalité listée ici correspond à un module réellement implémenté et déployé
// aujourd'hui, à l'exception des deux marquées "À venir" — jamais présentées comme disponibles
// alors qu'elles ne le sont pas. "Inscriptions" et "Évaluations" reprennent les noms réels des
// modules du produit (respectivement les inscriptions par classe et les évaluations notées),
// plutôt que les libellés génériques "Admissions"/"Examens" qui ne correspondent à aucun module
// existant sous ce nom précis.
const FEATURES: { icon: typeof UsersIcon; title: string; available: boolean }[] = [
  { icon: UsersIcon, title: "Gestion des élèves", available: true },
  { icon: GraduationCapIcon, title: "Gestion des enseignants", available: true },
  { icon: LayersIcon, title: "Classes", available: true },
  { icon: FolderIcon, title: "Inscriptions", available: true },
  { icon: ClipboardCheckIcon, title: "Présences", available: true },
  { icon: ChartBarIcon, title: "Notes", available: true },
  { icon: CheckCircleIcon, title: "Évaluations", available: true },
  { icon: BookOpenIcon, title: "Bulletins", available: true },
  { icon: FolderIcon, title: "Devoirs", available: false },
  { icon: CalendarIcon, title: "Emploi du temps", available: false },
  { icon: CreditCardIcon, title: "Frais scolaires", available: true },
  { icon: CreditCardIcon, title: "Paiements", available: true },
  { icon: BellIcon, title: "Notifications", available: true },
  { icon: MessageSquareIcon, title: "Communication", available: true },
  { icon: UsersIcon, title: "Portail parents", available: true },
  { icon: TrendingUpIcon, title: "Tableaux de bord", available: true },
];

export function FeatureGrid() {
  return (
    <section id="fonctionnalites" className="bg-white py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">
            Tout ce dont votre établissement a besoin.
          </h2>
        </ScrollReveal>

        <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature, i) => {
            const Icon = feature.icon;
            return (
              <ScrollReveal key={feature.title} delayMs={(i % 4) * 60}>
                <div className="group flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-blue/40 hover:shadow-md">
                  <span
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                      feature.available ? "bg-brand-blue/10 text-brand-blue" : "bg-slate-100 text-slate-400"
                    }`}
                  >
                    <Icon className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-brand-text">{feature.title}</p>
                    {!feature.available && (
                      <span className="mt-1 inline-block rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                        À venir
                      </span>
                    )}
                  </div>
                </div>
              </ScrollReveal>
            );
          })}
        </div>

        <ScrollReveal delayMs={200} className="mt-8 flex items-center justify-center gap-2 text-sm text-slate-400">
          <ShieldIcon className="h-4 w-4" />
          Fonctionnalités réellement disponibles dans la plateforme aujourd&apos;hui.
        </ScrollReveal>
      </div>
    </section>
  );
}
