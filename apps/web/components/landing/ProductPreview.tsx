import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { CheckCircleIcon, ClipboardCheckIcon, UsersIcon } from "@/components/landing/icons";

const STUDENTS = [
  { name: "Kofi Mensah", status: "Actif" },
  { name: "Ama Diallo", status: "Actif" },
  { name: "Yao Tchamba", status: "Actif" },
];

export function ProductPreview() {
  return (
    <section id="solutions" className="overflow-hidden bg-brand-bg py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-bold text-brand-text sm:text-4xl">
            Tout votre établissement, au même endroit.
          </h2>
        </ScrollReveal>

        <div className="relative mx-auto mt-16 max-w-3xl">
          {/* Carte principale */}
          <ScrollReveal delayMs={80}>
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
              <div className="mb-4 flex items-center gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-blue/10 text-brand-blue">
                  <UsersIcon className="h-5 w-5" />
                </span>
                <p className="text-sm font-semibold text-brand-text">Élèves — CE2 B</p>
              </div>
              <div className="divide-y divide-slate-100">
                {STUDENTS.map((student) => (
                  <div key={student.name} className="flex items-center justify-between py-2.5">
                    <span className="text-sm text-slate-700">{student.name}</span>
                    <span className="rounded-full bg-brand-blue/10 px-2.5 py-0.5 text-[11px] font-semibold text-brand-blue">
                      {student.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </ScrollReveal>

          {/* Petites cartes superposées */}
          <ScrollReveal
            delayMs={200}
            className="absolute -left-6 -top-8 hidden w-48 rotate-[-4deg] rounded-xl border border-slate-200 bg-white/95 p-4 shadow-lg backdrop-blur-sm sm:block lg:-left-16"
          >
            <div className="flex items-center gap-2">
              <ClipboardCheckIcon className="h-4 w-4 text-brand-cyan" />
              <p className="text-xs font-semibold text-brand-text">Présence</p>
            </div>
            <p className="mt-2 text-2xl font-bold text-brand-text">96%</p>
            <p className="text-[11px] text-slate-400">Cette semaine</p>
          </ScrollReveal>

          <ScrollReveal
            delayMs={280}
            className="absolute -bottom-8 -right-6 hidden w-48 rotate-[4deg] rounded-xl border border-slate-200 bg-white/95 p-4 shadow-lg backdrop-blur-sm sm:block lg:-right-16"
          >
            <div className="flex items-center gap-2">
              <CheckCircleIcon className="h-4 w-4 text-brand-blue" />
              <p className="text-xs font-semibold text-brand-text">Bulletins</p>
            </div>
            <p className="mt-2 text-2xl font-bold text-brand-text">12 publiés</p>
            <p className="text-[11px] text-slate-400">Ce trimestre</p>
          </ScrollReveal>
        </div>
      </div>
    </section>
  );
}
