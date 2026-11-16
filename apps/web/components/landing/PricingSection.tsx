import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { PricingSimulator } from "@/components/landing/PricingSimulator";
import { GiftIcon, MessageSquareIcon, WalletIcon } from "@/components/landing/icons";
import { whatsappLink } from "@/lib/landing/contact";
import { formatFcfa, priceFor, savingsPercent, type PublicPricing } from "@/lib/landing/pricing.mjs";

const OFFERS = [
  { months: 3, label: "Trimestre", per: "par trimestre" },
  { months: 6, label: "Semestre", per: "par semestre" },
  { months: 12, label: "Année", per: "par an" },
];

// Tarifs : montants de la grille ACTIVE (lus par la page côté serveur), jamais écrits ici. Sans
// grille lisible, la section propose de demander les tarifs sur WhatsApp.
export function PricingSection({ pricing }: { pricing: PublicPricing | null }) {
  const quarterly = priceFor(pricing, 3, 0);

  return (
    <section id="tarifs" className="bg-brand-bg py-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">Des tarifs simples et transparents.</h2>
          <p className="mt-4 text-lg text-slate-600">
            Un forfait de base jusqu&apos;à 100 élèves, puis un supplément selon l&apos;effectif. Plus la durée est
            longue, moins vous payez.
          </p>
        </ScrollReveal>

        <ScrollReveal className="mx-auto mt-10 max-w-4xl">
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center sm:flex-row sm:text-left">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white">
              <GiftIcon />
            </span>
            <div>
              <p className="text-lg font-semibold text-emerald-900">Premier trimestre offert</p>
              <p className="mt-1 text-sm text-emerald-800">
                Chaque nouvelle école utilise EduLinkage gratuitement pendant 3 mois, avec toutes les fonctionnalités.
                Vous ne payez qu&apos;à partir du trimestre suivant, si vous continuez.
              </p>
            </div>
          </div>
        </ScrollReveal>

        {pricing && quarterly !== null ? (
          <>
            <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
              {OFFERS.map((offer, i) => {
                const price = priceFor(pricing, offer.months, 0);
                const saving = savingsPercent(price, quarterly, offer.months);
                const highlighted = offer.months === 12;
                return (
                  <ScrollReveal key={offer.months} delayMs={i * 80}>
                    <div
                      className={`relative h-full rounded-2xl border bg-white p-6 ${
                        highlighted ? "border-brand-blue shadow-lg" : "border-slate-200"
                      }`}
                    >
                      {highlighted && (
                        <span className="absolute -top-3 left-6 rounded-full bg-brand-blue px-3 py-1 text-xs font-semibold text-white">
                          Le plus avantageux
                        </span>
                      )}
                      <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                        {offer.label} · {offer.months} mois
                      </p>
                      <p className="mt-4 text-sm text-slate-500">à partir de</p>
                      <p className="text-3xl font-bold text-brand-text">{price === null ? "Sur devis" : formatFcfa(price)}</p>
                      <p className="mt-1 text-sm text-slate-500">{offer.per}, jusqu&apos;à 100 élèves</p>
                      {saving > 0 && (
                        <p className="mt-4 inline-block rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                          {saving} % d&apos;économie par rapport au trimestre
                        </p>
                      )}
                    </div>
                  </ScrollReveal>
                );
              })}
            </div>

            <div className="mt-10 grid grid-cols-1 items-start gap-8 lg:grid-cols-2">
              <ScrollReveal>
                <PricingSimulator pricing={pricing} />
              </ScrollReveal>
              <ScrollReveal delayMs={100}>
                <div className="space-y-6 lg:pt-4">
                  <div className="flex gap-4">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-blue/10 text-brand-blue">
                      <WalletIcon className="h-5 w-5" />
                    </span>
                    <div>
                      <p className="font-semibold text-brand-text">Paiement par Mobile Money</p>
                      <p className="mt-1 text-sm leading-relaxed text-slate-600">
                        Payez par Flooz ou T-Money directement depuis l&apos;espace de votre école, ou auprès de notre
                        équipe. Un reçu est délivré à chaque paiement.
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-4">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-blue/10 text-brand-blue">
                      <GiftIcon className="h-5 w-5" />
                    </span>
                    <div>
                      <p className="font-semibold text-brand-text">Tout est inclus</p>
                      <p className="mt-1 text-sm leading-relaxed text-slate-600">
                        Toutes les fonctionnalités et tous les comptes (direction, enseignants, parents) sont compris
                        dans l&apos;abonnement, ainsi que les mises à jour.
                      </p>
                    </div>
                  </div>
                  <p className="text-sm text-slate-500">
                    Le prix dépend du nombre d&apos;élèves actifs au moment de la facture. Montants en FCFA.
                  </p>
                </div>
              </ScrollReveal>
            </div>
          </>
        ) : (
          <ScrollReveal className="mx-auto mt-10 max-w-xl rounded-2xl border border-slate-200 bg-white p-8 text-center">
            <p className="text-lg font-semibold text-brand-text">Tarifs sur demande</p>
            <p className="mt-2 text-sm text-slate-600">
              Écrivez-nous sur WhatsApp : nous vous communiquons le prix exact pour votre école.
            </p>
            <a
              href={whatsappLink()}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-6 inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
            >
              <MessageSquareIcon className="h-5 w-5" />
              Demander les tarifs
            </a>
          </ScrollReveal>
        )}
      </div>
    </section>
  );
}
