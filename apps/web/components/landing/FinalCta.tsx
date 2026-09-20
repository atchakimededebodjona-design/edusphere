import Link from "next/link";
import { ScrollReveal } from "@/components/landing/ScrollReveal";

export function FinalCta() {
  return (
    <section id="contact" className="relative overflow-hidden bg-brand-navy py-20">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand-blue/20 via-transparent to-brand-cyan/20"
      />
      <div className="relative mx-auto max-w-3xl px-4 text-center sm:px-6 lg:px-8">
        <ScrollReveal>
          <h2 className="text-3xl font-bold text-white sm:text-4xl">Prêt à connecter votre établissement ?</h2>
          <p className="mt-4 text-lg text-slate-300">
            Découvrez comment EduLinkage peut simplifier la gestion de votre école.
          </p>

          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            {/* Aucune adresse de contact réelle n'existe encore pour ce premier lancement — ancre
                interne plutôt qu'une URL/adresse inventée, conformément à la consigne. */}
            <a
              href="#contact"
              className="rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
            >
              Demander une démonstration
            </a>
            <Link
              href="/login"
              className="rounded-lg border border-white/20 px-6 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              Se connecter
            </Link>
          </div>

          <p className="mt-6 text-sm font-medium text-slate-400">Une école, des liens, un avenir.</p>
        </ScrollReveal>
      </div>
    </section>
  );
}
