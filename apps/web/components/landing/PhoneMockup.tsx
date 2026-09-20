import { BellIcon, CheckCircleIcon, CreditCardIcon } from "@/components/landing/icons";

// Composition illustrative de l'espace parent — écran fictif générique (aucun vrai compte, aucune
// vraie donnée), construite en React/Tailwind, pas une capture d'écran de l'application réelle.
export function PhoneMockup() {
  return (
    <div className="relative mx-auto w-64">
      <div
        aria-hidden="true"
        className="absolute -inset-8 -z-10 rounded-[3rem] bg-gradient-to-br from-brand-blue/20 to-brand-cyan/20 blur-3xl"
      />
      <div className="rounded-[2.25rem] border-[6px] border-brand-navy bg-brand-navy shadow-xl">
        <div className="relative overflow-hidden rounded-[1.75rem] bg-white">
          <div className="absolute left-1/2 top-2 h-1.5 w-16 -translate-x-1/2 rounded-full bg-slate-800/80" />

          <div className="bg-gradient-to-br from-brand-navy to-brand-blue px-5 pb-6 pt-8 text-white">
            <p className="text-xs text-slate-300">Bonjour,</p>
            <p className="text-sm font-semibold">Famille Kodjo</p>
          </div>

          <div className="-mt-4 space-y-3 rounded-t-2xl bg-white px-4 pb-6 pt-4">
            <div className="rounded-xl border border-slate-100 p-3 shadow-sm">
              <p className="text-xs font-semibold text-brand-text">Ama K.</p>
              <p className="text-[11px] text-slate-400">CM2 B</p>
              <div className="mt-2 flex items-center justify-between text-[11px]">
                <span className="flex items-center gap-1 text-brand-blue">
                  <CheckCircleIcon className="h-3.5 w-3.5" />
                  Présente aujourd&apos;hui
                </span>
                <span className="font-semibold text-brand-text">Moy. 15,4/20</span>
              </div>
            </div>

            <div className="rounded-xl border border-slate-100 p-3 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-text">
                  <CreditCardIcon className="h-3.5 w-3.5 text-brand-cyan" />
                  Frais scolaires
                </span>
                <span className="text-[11px] text-slate-400">2/3 réglés</span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-brand-blue to-brand-cyan" />
              </div>
            </div>

            <div className="rounded-xl border border-slate-100 p-3 shadow-sm">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold text-brand-text">
                <BellIcon className="h-3.5 w-3.5 text-brand-blue" />
                Bulletin du 2e trimestre publié
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
