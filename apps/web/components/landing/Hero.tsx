import { DashboardMockup } from "@/components/landing/DashboardMockup";

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
          <span className="inline-flex items-center rounded-full border border-brand-blue/20 bg-brand-blue/5 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-brand-blue">
            Plateforme de gestion scolaire
          </span>

          <h1 className="mt-5 text-4xl font-bold leading-tight tracking-tight text-brand-text sm:text-5xl">
            L&apos;école africaine mérite une plateforme{" "}
            <span className="bg-gradient-to-r from-brand-blue to-brand-cyan bg-clip-text text-transparent">
              pensée pour elle.
            </span>
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">
            EduLinkage connecte les écoles, les enseignants, les parents et les élèves dans un même
            espace simple, moderne et sécurisé.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a
              href="#solutions"
              className="rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-center text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
            >
              Découvrir EduLinkage
            </a>
            <a
              href="#contact"
              className="rounded-lg border border-slate-200 bg-white px-6 py-3 text-center text-sm font-semibold text-brand-text transition hover:border-brand-blue hover:text-brand-blue"
            >
              Demander une démonstration
            </a>
          </div>

          <p className="mt-6 text-sm font-medium text-slate-500">Une école, des liens, un avenir.</p>
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
