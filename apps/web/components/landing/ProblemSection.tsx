import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { ArrowRightIcon } from "@/components/landing/icons";

const PAIN_POINTS = [
  "Fichiers Excel dispersés entre plusieurs personnes",
  "Registres papier difficiles à conserver et à retrouver",
  "Informations éparpillées, jamais centralisées",
  "Communication fragmentée entre l'école et les familles",
  "Suivi des élèves complexe d'une classe à l'autre",
  "Bulletins et notes qui prennent un temps considérable",
];

export function ProblemSection() {
  return (
    <section className="bg-brand-bg py-20">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">
            Les écoles ne devraient pas gérer leur quotidien entre plusieurs outils.
          </h2>
        </ScrollReveal>

        <ScrollReveal delayMs={100}>
          <ul className="mx-auto mt-10 grid max-w-3xl grid-cols-1 gap-3 sm:grid-cols-2">
            {PAIN_POINTS.map((point) => (
              <li
                key={point}
                className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
              >
                {point}
              </li>
            ))}
          </ul>
        </ScrollReveal>

        <ScrollReveal delayMs={180}>
          <div className="mx-auto mt-10 flex max-w-md items-center justify-center gap-2 rounded-full bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-center text-sm font-semibold text-white">
            EduLinkage rassemble ces informations dans un même environnement
            <ArrowRightIcon />
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
