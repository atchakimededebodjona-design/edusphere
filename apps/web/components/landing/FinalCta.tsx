import Link from "next/link";
import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { MailIcon, MessageSquareIcon, PhoneIcon } from "@/components/landing/icons";
import { CONTACT_EMAIL, CONTACT_EMAIL_LINK, CONTACT_PHONE_DISPLAY, CONTACT_PHONE_LINK, whatsappLink } from "@/lib/landing/contact";

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
            Écrivez-nous sur WhatsApp ou par e-mail, ou appelez-nous : nous créons l&apos;espace de votre école et
            répondons à vos questions. Le premier trimestre est offert.
          </p>

          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <a
              href={whatsappLink()}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
            >
              <MessageSquareIcon className="h-5 w-5" />
              Écrire sur WhatsApp
            </a>
            <a
              href={CONTACT_PHONE_LINK}
              className="flex items-center justify-center gap-2 rounded-lg border border-white/20 px-6 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
            >
              <PhoneIcon className="h-5 w-5" />
              Appeler le {CONTACT_PHONE_DISPLAY}
            </a>
          </div>

          <a
            href={CONTACT_EMAIL_LINK}
            className="mt-4 inline-flex min-h-11 items-center justify-center gap-2 break-all text-sm font-semibold text-white underline-offset-4 hover:underline"
          >
            <MailIcon className="h-5 w-5 shrink-0" />
            {CONTACT_EMAIL}
          </a>

          <p className="mt-6 text-sm text-slate-400">
            Déjà client ?{" "}
            <Link href="/login" className="font-semibold text-white underline-offset-4 hover:underline">
              Se connecter
            </Link>
          </p>

          <p className="mt-2 text-sm font-medium text-slate-500">Une école, des liens, un avenir.</p>
        </ScrollReveal>
      </div>
    </section>
  );
}
