import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { PhoneMockup } from "@/components/landing/PhoneMockup";
import { BellIcon, CheckCircleIcon, ChartBarIcon, CreditCardIcon } from "@/components/landing/icons";

const PARENT_ITEMS = [
  { icon: CheckCircleIcon, label: "Présences" },
  { icon: ChartBarIcon, label: "Notes et bulletins" },
  { icon: CreditCardIcon, label: "Frais et paiements" },
  { icon: BellIcon, label: "Notifications" },
];

export function ParentPortalSection() {
  return (
    <section className="overflow-hidden bg-brand-navy py-20">
      <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 sm:px-6 lg:grid-cols-2 lg:px-8">
        <ScrollReveal>
          <h2 className="text-3xl font-bold text-white sm:text-4xl">
            Les parents restent connectés à la vie scolaire.
          </h2>
          <p className="mt-4 max-w-lg text-slate-300">
            Enfants, présences, notes, bulletins, frais, paiements et notifications — au même
            endroit, depuis un téléphone.
          </p>

          <ul className="mt-8 grid grid-cols-2 gap-4">
            {PARENT_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.label} className="flex items-center gap-2 text-sm text-slate-200">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-brand-cyan">
                    <Icon className="h-4 w-4" />
                  </span>
                  {item.label}
                </li>
              );
            })}
          </ul>

          <a
            href="#solutions"
            className="mt-8 inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
          >
            Découvrir l&apos;espace parent
          </a>
        </ScrollReveal>

        <ScrollReveal delayMs={120}>
          <PhoneMockup />
        </ScrollReveal>
      </div>
    </section>
  );
}
