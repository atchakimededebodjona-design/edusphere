"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextField, controlClass } from "@/components/ui/Field";
import { Alert, Badge, Card } from "@/components/ui/Surface";
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

  return (
    <form onSubmit={handleSubmit}>
      <Card className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Nouveau partenaire</h2>
          <p className="text-sm text-slate-600">Le contact reçoit par email un lien pour choisir son mot de passe.</p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <TextField label="Nom du partenaire" placeholder="Nom du partenaire" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <TextField label="Nom du contact" placeholder="Nom du contact" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          <TextField label="Email du contact" type="email" placeholder="Email du contact" value={email} onChange={(e) => setEmail(e.target.value)} />
          <TextField
            label="Téléphone"
            type="tel"
            placeholder="Téléphone (optionnel)"
            hint="Facultatif"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
        {success && <Alert tone="success">{success}</Alert>}
        <Button type="submit" icon="plus" disabled={submitting} className="self-start">
          {submitting ? "Création..." : "Créer le partenaire"}
        </Button>
      </Card>
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
      <span className="flex flex-wrap items-center gap-1">
        <span className="tabular-nums">{Number(partner.commission_rate)} %</span>
        {canManage && (
          <Button variant="quiet" size="sm" onClick={() => setEditing(true)}>
            Modifier
          </Button>
        )}
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        inputMode="decimal"
        aria-label={`Taux de commission de ${partner.display_name}`}
        className={`${controlClass} !min-h-9 !w-20`}
      />
      %
      <Button size="sm" disabled={saving} onClick={save}>
        Enregistrer
      </Button>
      <Button variant="secondary" size="sm" onClick={() => setEditing(false)}>
        Annuler
      </Button>
      {error && (
        <span role="alert" className="w-full text-xs font-medium text-red-700">
          {error}
        </span>
      )}
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
        { header: "Email", mobile: "full", render: (partner) => <span className="break-all">{partner.email ?? "—"}</span> },
        {
          header: "Statut",
          render: (partner) => <Badge tone={partner.status === "ACTIVE" ? "success" : "neutral"}>{partner.status === "ACTIVE" ? "Actif" : "Suspendu"}</Badge>,
        },
        { header: "Écoles inscrites", align: "right", render: (partner) => String(partner.enrollment_count) },
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
