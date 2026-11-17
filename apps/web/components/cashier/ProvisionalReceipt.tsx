"use client";

import { useEffect } from "react";
import { formatApiAmount } from "@/lib/fees/allocation";
import type { ProvisionalReceipt } from "@/lib/offline/outbox";

// Phase 32, lot 3 — reçu PROVISOIRE d'un encaissement fait sans internet, affiché et imprimable sans
// réseau (aucune requête : tout est gardé dans la boîte d'envoi). Le reçu officiel (`RCPT-…`, PDF du
// serveur) le remplace une fois l'encaissement envoyé ; il en reprend le numéro provisoire.

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  const time = date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  return `${day} à ${time}`;
}

const PRINT_ROOT_ID = "provisional-receipt-print";

function clearPrintedReceipt(): void {
  document.getElementById(PRINT_ROOT_ID)?.remove();
  delete document.documentElement.dataset.print;
}

/**
 * Imprime uniquement le reçu affiché : une copie est posée directement dans <body>, seule imprimée
 * (règles dans app/globals.css), en haut de la première page quelle que soit la mise en page de
 * l'écran. Gardée jusqu'à la fermeture du reçu : certains navigateurs mobiles préparent l'impression
 * après le retour de `window.print()`.
 */
export function printProvisionalReceipt(): void {
  const receipt = document.querySelector("[data-provisional-receipt]");
  if (!receipt) return;
  clearPrintedReceipt();
  const root = document.createElement("div");
  root.id = PRINT_ROOT_ID;
  const copy = receipt.cloneNode(true) as HTMLElement;
  copy.removeAttribute("data-provisional-receipt");
  root.appendChild(copy);
  document.body.appendChild(root);
  document.documentElement.dataset.print = "provisional-receipt";
  window.print();
}

export function ProvisionalReceiptCard({ receipt }: { receipt: ProvisionalReceipt }) {
  useEffect(() => clearPrintedReceipt, []);

  const rows: [string, string][] = [
    ["Date", formatDateTime(receipt.collectedAt)],
    ["Élève", `${receipt.student.lastName} ${receipt.student.firstName} (${receipt.student.matricule})`],
    ["Classe", receipt.student.className ?? "—"],
    ["Mode", "Espèces"],
  ];
  if (receipt.payerName) rows.push(["Payeur", receipt.payerName]);
  if (receipt.reference) rows.push(["Référence", receipt.reference]);
  rows.push(["Caissier", receipt.cashierName ?? "—"]);

  return (
    <article
      data-provisional-receipt
      aria-label="Reçu provisoire"
      className="flex flex-col gap-3 rounded border-2 border-dashed border-slate-400 bg-white p-4 text-sm text-slate-900"
    >
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{receipt.schoolName}</p>
        <h3 className="text-lg font-bold">REÇU PROVISOIRE</h3>
        <p data-testid="provisional-receipt-number" className="text-xl font-bold tracking-wide">
          {receipt.number}
        </p>
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-slate-500">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-300 text-left">
            <th className="py-1 font-medium">Frais</th>
            <th className="py-1 text-right font-medium">Montant</th>
          </tr>
        </thead>
        <tbody>
          {receipt.allocations.map((line) => (
            <tr key={line.name} className="border-b border-slate-100">
              <td className="py-1">{line.name}</td>
              <td className="py-1 text-right">{formatApiAmount(line.amount, receipt.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-base font-bold">Montant reçu : {formatApiAmount(receipt.amount, receipt.currency)}</p>
      <p className="text-xs text-slate-700">
        Encaissement enregistré sans connexion internet. Ce reçu provisoire sera remplacé par le reçu officiel
        (numéro RCPT-…) dès l&apos;envoi au serveur, qui reprendra le numéro {receipt.number}. Conservez-le jusqu&apos;à
        la remise du reçu officiel.
      </p>
    </article>
  );
}
