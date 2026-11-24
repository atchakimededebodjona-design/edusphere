import type { ReactNode } from "react";
import { LandingFooter } from "@/components/landing/LandingFooter";
import { LandingNav } from "@/components/landing/LandingNav";
import { ProtectedEmail } from "@/components/landing/ProtectedEmail";
import { CONTACT_PHONE_DISPLAY } from "@/lib/landing/contact";
import type { LegalIdentity } from "@/lib/legal/identity";

// 2026-11-24 — gabarit des pages juridiques (confidentialité, CGU, CGV) : en-tête et pied de page de
// l'accueil, texte en colonne lisible, sommaire. Les titres de section sont des h2 avec un identifiant,
// pour les liens directs (ex. /confidentialite#cookies).

export function LegalPage({
  title,
  updated,
  intro,
  sections,
}: {
  title: string;
  updated: string;
  intro: ReactNode;
  sections: { id: string; title: string; body: ReactNode }[];
}) {
  return (
    <>
      <LandingNav />
      <main className="bg-brand-bg">
        <article className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:py-16">
          <p className="text-sm font-semibold uppercase tracking-wide text-brand-blue">Informations légales</p>
          <h1 className="mt-2 text-3xl font-bold text-brand-text sm:text-4xl">{title}</h1>
          <p className="mt-2 text-sm text-slate-600">Dernière mise à jour : {updated}</p>
          <div className="mt-6 space-y-3 text-base leading-relaxed text-slate-700">{intro}</div>

          <nav aria-label="Sommaire" className="mt-8 rounded-xl border border-slate-200 bg-white p-5">
            <p className="text-sm font-semibold text-brand-text">Sommaire</p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
              {sections.map((section) => (
                <li key={section.id}>
                  <a href={`#${section.id}`} className="text-brand-blue underline-offset-2 hover:underline">
                    {section.title}
                  </a>
                </li>
              ))}
            </ol>
          </nav>

          {sections.map((section, index) => (
            <section key={section.id} aria-labelledby={section.id} className="mt-10 scroll-mt-24">
              <h2 id={section.id} className="text-xl font-bold text-brand-text">
                {index + 1}. {section.title}
              </h2>
              <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-700 [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-1">
                {section.body}
              </div>
            </section>
          ))}
        </article>
      </main>
      <LandingFooter />
    </>
  );
}

function emailParts(email: string): [string, string] | undefined {
  const at = email.lastIndexOf("@");
  return at > 0 && at < email.length - 1 ? [email.slice(0, at), email.slice(at + 1)] : undefined;
}

/** Identité de l'exploitant : seuls les champs renseignés sur le serveur s'affichent. */
export function LegalIdentityBlock({ identity }: { identity: LegalIdentity }) {
  const company = [identity.legal_name, identity.legal_form].filter(Boolean).join(", ");
  const rows: [string, ReactNode][] = [
    ["Nom commercial", identity.trade_name || "EduLinkage"],
    ...(company ? ([["Société", company]] as [string, ReactNode][]) : []),
    ...(identity.address ? ([["Adresse", identity.address]] as [string, ReactNode][]) : []),
    ...(identity.rccm ? ([["RCCM", identity.rccm]] as [string, ReactNode][]) : []),
    ...(identity.nif ? ([["NIF", identity.nif]] as [string, ReactNode][]) : []),
    ["Téléphone", identity.phone || CONTACT_PHONE_DISPLAY],
    [
      "E-mail",
      // Adresse assemblée dans le navigateur (anti-spam), celle du serveur si elle est renseignée.
      <ProtectedEmail
        key="email"
        parts={emailParts(identity.email)}
        className="inline-flex min-h-6 items-center break-all text-brand-blue underline-offset-2 hover:underline"
      />,
    ],
  ];
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 rounded-xl border border-slate-200 bg-white p-5 text-sm sm:grid-cols-[max-content_1fr]">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="font-semibold text-brand-text">{label}</dt>
          <dd className="break-words text-slate-700">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
