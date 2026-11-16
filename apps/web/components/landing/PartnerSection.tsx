import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { ChartBarIcon, MessageSquareIcon, UsersIcon, WalletIcon } from "@/components/landing/icons";
import { PARTNER_WHATSAPP_MESSAGE, whatsappLink } from "@/lib/landing/contact";

// Programme partenaire (Phase 30, décisions du 2026-11-15) : 20 % par défaut, sur chaque paiement
// confirmé des écoles inscrites par le partenaire, sans limite de durée, versés manuellement.
const POINTS = [
  {
    icon: ChartBarIcon,
    title: "20 % de chaque abonnement payé",
    text: "Sur chaque paiement des écoles que vous avez inscrites, renouvellements compris, sans limite de durée.",
  },
  {
    icon: UsersIcon,
    title: "Votre espace partenaire",
    text: "Inscrivez vos écoles et suivez vos commissions, à recevoir et déjà reçues, depuis votre propre espace.",
  },
  {
    icon: WalletIcon,
    title: "Des versements simples",
    text: "Vos commissions vous sont versées par Mobile Money, par virement ou en espèces.",
  },
];

export function PartnerSection() {
  return (
    <section id="partenaires" className="bg-white py-20">
      <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 sm:px-6 lg:grid-cols-2 lg:px-8">
        <ScrollReveal>
          <span className="inline-flex items-center rounded-full border border-brand-blue/20 bg-brand-blue/5 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand-blue">
            Programme partenaire
          </span>
          <h2 className="mt-4 text-3xl font-bold text-brand-text sm:text-4xl">Devenez partenaire EduLinkage.</h2>
          <p className="mt-4 max-w-lg text-lg text-slate-600">
            Vous connaissez des écoles ? Faites-leur découvrir EduLinkage et recevez une commission sur chacun de leurs
            abonnements.
          </p>
          <a
            href={whatsappLink(PARTNER_WHATSAPP_MESSAGE)}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
          >
            <MessageSquareIcon className="h-5 w-5" />
            Devenir partenaire
          </a>
        </ScrollReveal>

        <div className="space-y-4">
          {POINTS.map((point, i) => {
            const Icon = point.icon;
            return (
              <ScrollReveal key={point.title} delayMs={i * 80}>
                <div className="flex gap-4 rounded-2xl border border-slate-200 bg-brand-bg p-5">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-brand-blue shadow-sm">
                    <Icon className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="font-semibold text-brand-text">{point.title}</p>
                    <p className="mt-1 text-sm leading-relaxed text-slate-600">{point.text}</p>
                  </div>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
