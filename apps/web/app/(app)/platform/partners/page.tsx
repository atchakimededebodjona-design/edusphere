"use client";

import { useState } from "react";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { platformCommissions } from "@/lib/commissions/client";
import { createPlatformPartner, listPlatformPartners, type PlatformPartner } from "@/lib/platform/client";
import { formatDate, PlatformListPage } from "../PlatformListPage";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function CreatePartnerForm({ onCreated }: { onCreated: () => void }) {
  const [displayName, setDisplayName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (displayName.trim().length < 2 || fullName.trim().length < 2) {
      setError("Le nom du partenaire et celui du contact doivent comporter au moins 2 caractères.");
      return;
    }
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Adresse email invalide.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await createPlatformPartner({
        display_name: displayName.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim() || null,
      });
      setSuccess(`Partenaire « ${created.partner.display_name} » créé. Un lien d'activation a été envoyé par email.`);
      setDisplayName("");
      setFullName("");
      setEmail("");
      setPhone("");
      onCreated();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const input = "rounded border border-slate-300 px-3 py-2 text-sm";
  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded border border-slate-200 p-4">
      <h2 className="font-semibold text-slate-900">Nouveau partenaire</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <input className={input} placeholder="Nom du partenaire" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        <input className={input} placeholder="Nom du contact" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        <input className={input} type="email" placeholder="Email du contact" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className={input} placeholder="Téléphone (optionnel)" value={phone} onChange={(e) => setPhone(e.target.value)} />
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {success && <p className="text-sm text-emerald-700">{success}</p>}
      <div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {submitting ? "Création..." : "Créer le partenaire"}
        </button>
      </div>
    </form>
  );
}

/** Taux de commission du partenaire (migration 0031) : s'applique aux PROCHAINES commissions ; les
 * commissions existantes gardent le leur. Modifiable avec `platform.commissions.manage`. */
function CommissionRateCell({ partner, canManage, onSaved }: { partner: PlatformPartner; canManage: boolean; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(Number(partner.commission_rate)));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    const rate = Number(value.replace(",", "."));
    if (!Number.isFinite(rate) || rate < 0 || rate > 100) {
      setError("Taux entre 0 et 100.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await platformCommissions.setRate(partner.id, String(rate));
      setEditing(false);
      onSaved();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <span className="flex items-center gap-2">
        {Number(partner.commission_rate)} %
        {canManage && (
          <button type="button" onClick={() => setEditing(true)} className="text-sky-700 underline">
            Modifier
          </button>
        )}
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-2">
      <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" className="w-16 rounded border border-slate-300 px-2 py-1" />
      %
      <button type="button" disabled={saving} onClick={save} className="text-emerald-700 underline disabled:opacity-50">
        Enregistrer
      </button>
      <button type="button" onClick={() => setEditing(false)} className="text-slate-600 underline">
        Annuler
      </button>
      {error && <span className="text-xs text-red-700">{error}</span>}
    </span>
  );
}

export default function PlatformPartnersPage() {
  const { permissions } = useAuth();
  const canManageCommissions = permissions.includes("platform.commissions.manage");
  const [reloadKey, setReloadKey] = useState(0);
  return (
    <PlatformListPage<PlatformPartner>
      title="Partenaires"
      description="Partenaires commerciaux et nombre d'écoles inscrites par chacun."
      fetchPage={listPlatformPartners}
      rowKey={(partner) => partner.id}
      reloadKey={reloadKey}
      columns={[
        { header: "Partenaire", render: (partner) => partner.display_name },
        { header: "Email", render: (partner) => partner.email ?? "—" },
        { header: "Statut", render: (partner) => (partner.status === "ACTIVE" ? "Actif" : "Suspendu") },
        { header: "Écoles inscrites", render: (partner) => String(partner.enrollment_count) },
        {
          header: "Commission",
          render: (partner) => (
            <CommissionRateCell partner={partner} canManage={canManageCommissions} onSaved={() => setReloadKey((k) => k + 1)} />
          ),
        },
        { header: "Créé le", render: (partner) => formatDate(partner.created_at) },
      ]}
    >
      <CreatePartnerForm onCreated={() => setReloadKey((k) => k + 1)} />
    </PlatformListPage>
  );
}
