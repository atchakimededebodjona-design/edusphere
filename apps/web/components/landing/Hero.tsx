import { DashboardMockup } from "@/components/landing/DashboardMockup";
import { GiftIcon, MessageSquareIcon, PhoneIcon } from "@/components/landing/icons";
import { CONTACT_PHONE_DISPLAY, CONTACT_PHONE_LINK, whatsappLink } from "@/lib/landing/contact";

export function Hero() {
  return (
    <section id="accueil" className="relative overflow-hidden bg-brand-bg">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-gradient-to-br from-brand-blue/20 to-brand-cyan/20 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-32 top-24 h-80 w-80 rounded-full bg-gradient-to-tr from-brand-cyan/20 to-brand-blue/20 blur-3xl"
      />

      <div className="relative mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:gap-8 lg:px-8 lg:py-24">
        <div className="animate-fade-in motion-reduce:animate-none">
          <a
            href="#tarifs"
            className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-emerald-700 transition hover:border-emerald-300"
          >
            <GiftIcon className="h-4 w-4" />
            Premier trimestre offert
          </a>

          <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-brand-text sm:text-5xl">
            L&apos;école africaine mérite une plateforme{" "}
            <span className="bg-gradient-to-r from-brand-blue to-brand-cyan bg-clip-text text-transparent">
              pensée pour elle.
            </span>
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">
            Élèves, présences, notes, bulletins, frais scolaires et caisse : EduLinkage réunit toute la
            gestion de votre école et relie la direction, les enseignants et les parents.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a
              href={whatsappLink()}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-center text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
            >
              <MessageSquareIcon className="h-5 w-5" />
              Essayer gratuitement
            </a>
            <a
              href="#tarifs"
              className="rounded-lg border border-slate-200 bg-white px-6 py-3 text-center text-sm font-semibold text-brand-text transition hover:border-brand-blue hover:text-brand-blue"
            >
              Voir les tarifs
            </a>
          </div>
          <p className="mt-3 text-sm text-slate-600">
            Premier trimestre offert. Écrivez-nous sur WhatsApp : nous créons l&apos;espace de votre école avec vous.
          </p>

          <a
            href={CONTACT_PHONE_LINK}
            className="mt-4 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-slate-600 transition hover:text-brand-blue"
          >
            <PhoneIcon className="h-4 w-4" />
            Ou appelez-nous au {CONTACT_PHONE_DISPLAY}
          </a>
        </div>

        <div
          className="animate-slide-up motion-reduce:animate-none"
          style={{ animationDelay: "0.15s" }}
        >
          <DashboardMockup />
        </div>
      </div>
    </section>
  );
}
