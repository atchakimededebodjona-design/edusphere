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

// Uniquement des modules en service en production (2026-11-16) : aucune fonctionnalité « à venir »
// n'est affichée. Chaque libellé décrit ce que l'école peut faire aujourd'hui.
const FEATURES: { icon: typeof UsersIcon; title: string; text: string }[] = [
  { icon: UsersIcon, title: "Élèves et inscriptions", text: "Fiches élèves, inscriptions par classe, passages en masse." },
  { icon: GraduationCapIcon, title: "Enseignants", text: "Affectations et espace enseignant dédié." },
  { icon: LayersIcon, title: "Classes et matières", text: "Années scolaires, périodes, niveaux, classes." },
  { icon: ClipboardCheckIcon, title: "Présences", text: "Appel par classe, retards, taux de présence." },
  { icon: ChartBarIcon, title: "Notes et évaluations", text: "Saisie des notes et moyennes calculées." },
  { icon: BookOpenIcon, title: "Bulletins PDF", text: "Générés en un clic, avec QR code de vérification." },
  { icon: CreditCardIcon, title: "Frais scolaires", text: "Échéanciers, paiements, reçus et impayés." },
  { icon: FolderIcon, title: "Caisse de l'école", text: "Ouverture, mouvements et clôture de caisse." },
  { icon: BellIcon, title: "Rappels d'impayés", text: "Les parents sont prévenus des frais en retard." },
  { icon: MessageSquareIcon, title: "Annonces", text: "Informez parents et enseignants en un message." },
  { icon: BellIcon, title: "Notifications", text: "Chacun est averti de ce qui le concerne." },
  { icon: CheckCircleIcon, title: "Portail parents", text: "Présences, notes, bulletins et frais de l'enfant." },
  { icon: TrendingUpIcon, title: "Tableaux de bord", text: "Les chiffres clés de l'établissement." },
  { icon: ShieldIcon, title: "Journal d'activité", text: "Qui a fait quoi, et quand, dans l'école." },
  { icon: UsersIcon, title: "Comptes et rôles", text: "Chacun n'accède qu'à ce qui le concerne." },
  { icon: CalendarIcon, title: "Plusieurs établissements", text: "Un groupe scolaire, plusieurs écoles." },
];

export function FeatureGrid() {
  return (
    <section id="fonctionnalites" className="bg-white py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">
            Tout ce dont votre établissement a besoin, déjà disponible.
          </h2>
        </ScrollReveal>

        <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature, i) => {
            const Icon = feature.icon;
            return (
              <ScrollReveal key={feature.title} delayMs={(i % 4) * 60}>
                <div className="group flex h-full items-start gap-3 rounded-xl border border-slate-200 bg-white p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-blue/40 hover:shadow-md">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-blue/10 text-brand-blue">
                    <Icon className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-brand-text">{feature.title}</p>
                    <p className="mt-1 text-sm leading-snug text-slate-500">{feature.text}</p>
                  </div>
                </div>
              </ScrollReveal>
            );
          })}
        </div>

        <ScrollReveal delayMs={200} className="mt-8 flex items-center justify-center gap-2 text-sm text-slate-400">
          <ShieldIcon className="h-4 w-4" />
          Toutes ces fonctionnalités sont en service aujourd&apos;hui, sur ordinateur comme sur téléphone.
        </ScrollReveal>
      </div>
    </section>
  );
}
