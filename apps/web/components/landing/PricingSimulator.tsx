"use client";

import { useState } from "react";
import { whatsappLink } from "@/lib/landing/contact";
import { formatFcfa, priceFor, type PublicPricing } from "@/lib/landing/pricing.mjs";
import { MessageSquareIcon } from "@/components/landing/icons";

const DURATIONS = [
  { months: 3, label: "Trimestre" },
  { months: 6, label: "Semestre" },
  { months: 12, label: "Année" },
];
const MAX_STUDENTS = 20000;

// Simulateur : l'école saisit son effectif et voit le prix exact de chaque durée, calculé à partir
// de la grille active reçue par la page (aucun appel réseau depuis le navigateur).
export function PricingSimulator({ pricing }: { pricing: PublicPricing }) {
  const [input, setInput] = useState("180");
  const parsed = Number.parseInt(input, 10);
  const students = Number.isInteger(parsed) && parsed >= 0 && parsed <= MAX_STUDENTS ? parsed : null;
  const message =
    students === null
      ? undefined
      : `Bonjour, je souhaite découvrir EduLinkage pour mon école (environ ${students} élèves).`;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <h3 className="text-lg font-semibold text-brand-text">Calculez le prix pour votre école</h3>
      <label htmlFor="simulateur-effectif" className="mt-4 block text-sm font-medium text-slate-600">
        Nombre d&apos;élèves
      </label>
      <input
        id="simulateur-effectif"
        type="number"
        inputMode="numeric"
        min={0}
        max={MAX_STUDENTS}
        step={1}
        value={input}
        onChange={(event) => setInput(event.target.value)}
        className="mt-2 w-full rounded-lg border border-slate-300 px-4 py-3 text-lg font-semibold text-brand-text focus:border-brand-blue focus:outline-none focus:ring-2 focus:ring-brand-blue/20"
      />

      <dl className="mt-6 divide-y divide-slate-100" aria-live="polite">
        {DURATIONS.map((duration) => {
          const price = students === null ? null : priceFor(pricing, duration.months, students);
          return (
            <div key={duration.months} className="flex items-baseline justify-between gap-4 py-3">
              <dt className="text-sm text-slate-600">
                {duration.label} <span className="text-slate-600">({duration.months} mois)</span>
              </dt>
              <dd className="text-right text-base font-semibold text-brand-text">
                {students === null ? "—" : price === null ? "Sur devis" : formatFcfa(price)}
              </dd>
            </div>
          );
        })}
      </dl>

      <a
        href={whatsappLink(message)}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-6 flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
      >
        <MessageSquareIcon className="h-5 w-5" />
        Demander l&apos;ouverture de mon école
      </a>
    </div>
  );
}
