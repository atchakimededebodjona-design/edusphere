"use client";

import { useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage, useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import {
  deactivatePlatformAccount,
  deletePlatformAccount,
  listPlatformAccounts,
  reactivatePlatformAccount,
  type PlatformAccount,
} from "@/lib/platform/client";
import { formatDate } from "../PlatformListPage";

const PAGE_SIZE = 20;
const PLATFORM_ROLES = ["PLATFORM_OWNER", "SUPER_ADMIN", "PLATFORM_SUPPORT"];

// Comptes de la plateforme (2026-11-18 : retrait des comptes). « Désactiver » bloque l'accès tout de
// suite et se réactive à volonté ; « Supprimer » efface définitivement les données personnelles, mais
// garde l'historique (« Compte supprimé »). Contrôles réels côté API (`platform.accounts.manage`) :
// jamais son propre compte ni un compte plateforme ; un partenaire se désactive seulement.
export default function PlatformAccountsPage() {
  const { user, permissions } = useAuth();
  const canManage = permissions.includes("platform.accounts.manage");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [confirmingDeactivate, setConfirmingDeactivate] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<PlatformAccount | null>(null);
  const [confirmEmail, setConfirmEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => {
      setSearch(query.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(id);
  }, [query]);

  const { data, error, isLoading, isRefreshing, retry } = useAsyncData(
    () => listPlatformAccounts(page, PAGE_SIZE, search),
    [page, search, reloadKey],
  );

  async function run(action: () => Promise<PlatformAccount>, success: string) {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      setConfirmingDeactivate(null);
      setDeleting(null);
      setConfirmEmail("");
      setReloadKey((key) => key + 1);
    } catch (err) {
      setActionError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function startDelete(account: PlatformAccount) {
    setDeleting(account);
    setConfirmEmail("");
    setConfirmingDeactivate(null);
    setActionError(null);
    setNotice(null);
  }

  const emailMatches = deleting !== null && confirmEmail.trim().toLowerCase() === deleting.email.trim().toLowerCase();

  function actions(account: PlatformAccount) {
    if (account.deleted_at) return null;
    if (account.id === user?.id) return <span className="text-xs text-slate-400">Votre compte</span>;
    if (account.role_codes.some((code) => PLATFORM_ROLES.includes(code))) {
      return <span className="text-xs text-slate-400">Compte plateforme</span>;
    }
    const partner = account.role_codes.includes("PARTNER_ADMIN");
    return (
      <span className="flex flex-wrap items-center gap-3">
        {account.is_active ? (
          confirmingDeactivate === account.id ? (
            <span className="flex items-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  run(
                    () => deactivatePlatformAccount(account.id),
                    `Compte de ${account.full_name} désactivé : il ne peut plus se connecter.`,
                  )
                }
                className="font-medium text-amber-800 underline disabled:opacity-50"
              >
                Confirmer la désactivation
              </button>
              <button type="button" onClick={() => setConfirmingDeactivate(null)} className="text-slate-600 underline">
                Annuler
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirmingDeactivate(account.id)} className="text-amber-800 underline">
              Désactiver
            </button>
          )
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(
                () => reactivatePlatformAccount(account.id),
                `Compte de ${account.full_name} réactivé : il peut de nouveau se connecter.`,
              )
            }
            className="text-emerald-800 underline disabled:opacity-50"
          >
            Réactiver
          </button>
        )}
        {!partner && (
          <button type="button" onClick={() => startDelete(account)} className="text-red-700 underline">
            Supprimer
          </button>
        )}
      </span>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Comptes</h1>
        <p className="text-sm text-slate-600">
          Comptes utilisateurs de la plateforme.
          {canManage &&
            " « Désactiver » bloque l'accès tout de suite et se réactive à volonté. « Supprimer » efface définitivement le nom, l'email et le téléphone ; l'historique reste, signé « Compte supprimé »."}
        </p>
      </div>

      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Rechercher un nom ou un email"
        aria-label="Rechercher un compte"
        className="w-full max-w-md rounded border border-slate-300 px-3 py-2 text-sm"
      />

      {notice && (
        <p role="status" className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {actionError}
        </p>
      )}

      {deleting && (
        <div
          data-testid="delete-account-panel"
          className="flex flex-col gap-3 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-950"
        >
          <p className="font-semibold">
            Supprimer définitivement le compte de {deleting.full_name} ({deleting.email}) ?
          </p>
          <ul className="list-disc pl-5">
            <li>
              Nom, email, téléphone et mot de passe sont effacés ; rôles, affectations, liens de tuteur et sessions sont
              retirés.
            </li>
            <li>L&apos;historique (paiements, caisses, appels, notes…) reste, signé « Compte supprimé ».</li>
            <li>L&apos;email redevient libre pour un nouveau compte. Cette suppression ne peut pas être annulée.</li>
          </ul>
          <label className="flex flex-col gap-1">
            Pour confirmer, saisissez l&apos;email du compte :
            <input
              value={confirmEmail}
              onChange={(event) => setConfirmEmail(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              className="w-full max-w-md rounded border border-red-300 bg-white px-3 py-2"
            />
          </label>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={busy || !emailMatches}
              onClick={() =>
                run(
                  () => deletePlatformAccount(deleting.id, confirmEmail.trim()),
                  `Compte de ${deleting.full_name} supprimé définitivement.`,
                )
              }
              className="rounded bg-red-700 px-3 py-2 font-medium text-white hover:bg-red-800 disabled:opacity-50"
            >
              {busy ? "Suppression..." : "Supprimer définitivement"}
            </button>
            <button type="button" onClick={() => setDeleting(null)} className="px-2 py-2 text-slate-700 underline">
              Annuler
            </button>
          </div>
        </div>
      )}

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement...</p>}

      {data && (
        <>
          <p className="text-sm text-slate-500">
            {data.total} résultat{data.total > 1 ? "s" : ""}
            {isRefreshing && " — actualisation..."}
          </p>
          {data.items.length === 0 ? (
            <p className="text-sm text-slate-500">Aucun compte.</p>
          ) : (
            <div className="overflow-x-auto rounded border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    {["Nom", "Email", "Rôles", "Statut", "Créé le", ...(canManage ? ["Actions"] : [])].map((header) => (
                      <th key={header} className="px-3 py-2 text-left font-medium text-slate-600">
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((account) => (
                    <tr key={account.id} data-testid={`account-${account.id}`}>
                      <td className="px-3 py-2 text-slate-700">{account.full_name}</td>
                      <td className="px-3 py-2 text-slate-700">{account.deleted_at ? "—" : account.email}</td>
                      <td className="px-3 py-2 text-slate-700">{account.role_codes.join(", ") || "—"}</td>
                      <td className="px-3 py-2">
                        {account.deleted_at ? (
                          <span className="text-slate-500">Supprimé le {formatDate(account.deleted_at)}</span>
                        ) : account.is_active ? (
                          <span className="text-emerald-800">Actif</span>
                        ) : (
                          <span className="font-medium text-amber-800">Désactivé</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-700">{formatDate(account.created_at)}</td>
                      {canManage && <td className="px-3 py-2">{actions(account)}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.total_pages > 1 && (
            <div className="flex items-center gap-3 text-sm">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40"
              >
                Précédent
              </button>
              <span className="text-slate-600">
                Page {data.page} / {data.total_pages}
              </span>
              <button
                type="button"
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded border border-slate-300 px-3 py-1 disabled:opacity-40"
              >
                Suivant
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
