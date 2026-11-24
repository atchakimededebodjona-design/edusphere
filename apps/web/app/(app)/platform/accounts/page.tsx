"use client";

import { DataTable, Pager, TableSkeleton } from "@/components/ui/DataTable";
import { Badge, EmptyState } from "@/components/ui/Surface";
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
    if (account.id === user?.id) return <span className="text-xs text-slate-600">Votre compte</span>;
    if (account.role_codes.some((code) => PLATFORM_ROLES.includes(code))) {
      return <span className="text-xs text-slate-600">Compte plateforme</span>;
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
                className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-amber-800 hover:bg-amber-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Confirmer la désactivation
              </button>
              <button type="button" onClick={() => setConfirmingDeactivate(null)} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
                Annuler
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirmingDeactivate(account.id)} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-amber-800 hover:bg-amber-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
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
            className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-emerald-800 hover:bg-emerald-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Réactiver
          </button>
        )}
        {!partner && (
          <button type="button" onClick={() => startDelete(account)} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
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
        className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 max-w-md"
      />

      {notice && (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
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
              className="block w-full min-h-11 rounded-lg border border-red-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 max-w-md"
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
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-red-700 px-4 text-sm font-medium text-white hover:bg-red-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
            >
              {busy ? "Suppression..." : "Supprimer définitivement"}
            </button>
            <button type="button" onClick={() => setDeleting(null)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
              Annuler
            </button>
          </div>
        </div>
      )}

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <TableSkeleton />}

      {data && (
        <>
          <p className="text-sm text-slate-600" aria-live="polite">
            {data.total} résultat{data.total > 1 ? "s" : ""}
            {isRefreshing && " — actualisation..."}
          </p>
          <DataTable
            caption="Comptes"
            rows={data.items}
            rowKey={(account) => account.id}
            rowTestId={(account) => `account-${account.id}`}
            rowTone={(account) => (account.deleted_at ? "muted" : undefined)}
            empty={<EmptyState icon="users" title="Aucun compte." />}
            columns={[
              { key: "name", header: "Nom", mobile: "title", cell: (account) => account.full_name },
              {
                key: "email",
                header: "Email",
                mobile: "full",
                cell: (account) => <span className="break-all">{account.deleted_at ? "—" : account.email}</span>,
              },
              { key: "roles", header: "Rôles", cell: (account) => account.role_codes.join(", ") || "—" },
              {
                key: "status",
                header: "Statut",
                cell: (account) =>
                  account.deleted_at ? (
                    <Badge tone="neutral">Supprimé le {formatDate(account.deleted_at)}</Badge>
                  ) : account.is_active ? (
                    <Badge tone="success">Actif</Badge>
                  ) : (
                    <Badge tone="warning">Désactivé</Badge>
                  ),
              },
              { key: "created", header: "Créé le", cell: (account) => formatDate(account.created_at) },
              ...(canManage
                ? [{ key: "actions", header: "Actions", mobile: "full" as const, cell: (account: (typeof data.items)[number]) => actions(account) }]
                : []),
            ]}
          />
          <Pager page={data.page} totalPages={data.total_pages} onPage={(next) => setPage(Math.max(1, next))} />
        </>
      )}
    </div>
  );
}
