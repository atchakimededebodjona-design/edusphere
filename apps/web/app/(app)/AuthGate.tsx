"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  isParentOnlyAccount,
  isPartnerOnlyAccount,
  isPlatformAdmin,
  isPlatformOwnerOnlyAccount,
  isTeacherOnlyAccount,
} from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-8 text-center">
      {children}
    </div>
  );
}

function ErrorRetryScreen({
  message,
  onRetry,
  onReconnect,
}: {
  message: string;
  onRetry: () => void;
  onReconnect: () => void;
}) {
  return (
    <Centered>
      <p role="alert" className="max-w-sm text-sm text-red-700">
        {message}
      </p>
      <div className="flex gap-3">
        <button type="button" onClick={onRetry} className="rounded bg-slate-900 px-4 py-2 text-sm text-white">
          Réessayer
        </button>
        <button
          type="button"
          onClick={onReconnect}
          className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700"
        >
          Se reconnecter
        </button>
      </div>
    </Centered>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const {
    status,
    user,
    roles,
    organizationContextStatus,
    availableOrganizations,
    organizationContextError,
    selectOrganization,
    schoolContextStatus,
    availableSchools,
    schoolContextError,
    selectSchool,
    retryTenantContext,
    logout,
  } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // Phase 28A — un compte PARENT n'a pas sa place dans l'espace admin, même atteint directement
  // (URL tapée à la main, favori, rechargement de page) plutôt que via la connexion (déjà traitée
  // dans app/(auth)/login/page.tsx). Vérifié dès que le rôle est connu, AVANT toute résolution
  // organisation/école (qui n'a pas de sens pour ce compte — voir lib/auth/roles.ts) : un parent
  // ne doit jamais se retrouver bloqué sur un écran "choisissez une école" qui ne le concerne pas.
  const isParent = status === "authenticated" && isParentOnlyAccount(roles);

  useEffect(() => {
    if (isParent) router.replace("/parent");
  }, [isParent, router]);

  // Portail enseignant — un enseignant pur n'a pas sa place dans l'espace admin (menus École,
  // Utilisateurs, Frais...) : il est renvoyé vers `/teacher`, même atteint directement par URL.
  // La protection réelle reste côté backend (403 sur les endpoints admin pour un TEACHER seul).
  const isTeacher = status === "authenticated" && isTeacherOnlyAccount(user, roles);

  useEffect(() => {
    if (isTeacher) router.replace("/teacher");
  }, [isTeacher, router]);

  // Correction du flux super administrateur plateforme — un compte is_platform_admin n'a
  // structurellement aucune organisation/école (voir lib/auth/roles.ts::isPlatformAdmin) : la
  // résolution tenant ci-dessous (organizationContextStatus/schoolContextStatus) ne le concerne
  // jamais et finirait toujours en "empty". Contrairement au cas PARENT, pas de redirection —
  // `{children}` reste rendu directement, `/dashboard` choisit lui-même la vue plateforme
  // (voir app/(app)/dashboard/page.tsx) sans dépendre du contexte organisation/école.
  const isPlatform = status === "authenticated" && isPlatformAdmin(user);

  // PR #17 — routage par rôle des espaces Propriétaire de la plateforme / Partenaire.
  //
  // ATTENTION : CE ROUTAGE (et le filtrage du menu dans components/app-shell/Nav.tsx) N'EST PAS
  // UNE FRONTIÈRE DE SÉCURITÉ. Il ne sert qu'à éviter qu'un compte atterrisse sur un écran qui ne
  // le concerne pas. Toute la protection réelle est côté API : permissions RBAC `platform.*` /
  // `partner.*` vérifiées sur chaque endpoint, aucune permission scolaire pour PLATFORM_OWNER ni
  // PARTNER_ADMIN, et RLS Postgres qui ne montre AUCUNE ligne tenant à un partenaire (voir
  // apps/api/app/core/tenancy.py). Masquer ou afficher un lien ici ne donne ni ne retire jamais
  // aucun accès.
  //
  // - PLATFORM_OWNER : `is_platform_admin=true` côté serveur, donc déjà couvert par `isPlatform`
  //   ci-dessus (accueil plateforme sur /dashboard, menu plateforme uniquement).
  // - PARTNER_ADMIN : aucune organisation/école (résolution tenant sans objet) — renvoyé vers
  //   `/partner` depuis toute autre page de l'espace `(app)`.
  const isPartner = status === "authenticated" && isPartnerOnlyAccount(user, roles);
  const partnerOutsideOwnArea = isPartner && !(pathname === "/partner" || pathname.startsWith("/partner/"));

  useEffect(() => {
    if (partnerOutsideOwnArea) router.replace("/partner");
  }, [partnerOutsideOwnArea, router]);

  // - PLATFORM_OWNER pur : uniquement /dashboard (vue plateforme) et /platform/* — jamais un écran
  //   scolaire, même atteint par URL directe. (Toujours pas une frontière de sécurité.)
  const isOwnerOnly = status === "authenticated" && isPlatformOwnerOnlyAccount(user, roles);
  const ownerOutsideOwnArea =
    isOwnerOnly &&
    !(
      pathname === "/dashboard" ||
      pathname.startsWith("/dashboard/") ||
      pathname === "/platform" ||
      pathname.startsWith("/platform/")
    );

  useEffect(() => {
    if (ownerOutsideOwnArea) router.replace("/dashboard");
  }, [ownerOutsideOwnArea, router]);

  // Une fois l'application réellement entrée (organisation ET école résolues au moins une fois),
  // un changement volontaire de contexte déclenché depuis le sélecteur permanent
  // (components/app-shell/TenantSwitcher.tsx, via selectOrganization/selectSchool) fait
  // transitoirement repasser schoolContextStatus par "loading"/"selection-needed" — ce n'est plus
  // la résolution initiale et ne doit plus reprendre toute la page : le sélecteur affiche lui-même
  // ce sous-état (liste d'écoles, chargement, erreur) dans son propre panneau, sans quitter le
  // tableau de bord. Réinitialisé à la déconnexion pour qu'une reconnexion (même ou autre compte)
  // retraverse normalement le flux de résolution initiale ci-dessous.
  const hasEnteredAppRef = useRef(false);

  useEffect(() => {
    if (status === "anonymous") {
      hasEnteredAppRef.current = false;
      router.push("/login");
    }
  }, [status, router]);

  const reconnect = () => void logout().then(() => router.push("/login"));

  if (isParent) {
    return (
      <Centered>
        <p className="text-sm text-slate-500">Redirection vers votre espace...</p>
      </Centered>
    );
  }

  if (isPlatform) {
    if (ownerOutsideOwnArea) {
      return (
        <Centered>
          <p className="text-sm text-slate-500">Redirection vers l&apos;espace plateforme...</p>
        </Centered>
      );
    }
    return <>{children}</>;
  }

  if (isPartner) {
    if (partnerOutsideOwnArea) {
      return (
        <Centered>
          <p className="text-sm text-slate-500">Redirection vers votre espace partenaire...</p>
        </Centered>
      );
    }
    return <>{children}</>;
  }

  if (status === "authenticated" && organizationContextStatus === "resolved" && schoolContextStatus === "resolved") {
    hasEnteredAppRef.current = true;
  }

  if (hasEnteredAppRef.current && status === "authenticated") {
    return <>{children}</>;
  }

  if (status !== "authenticated" || organizationContextStatus === "loading") {
    return (
      <Centered>
        <p className="text-sm text-slate-500">Chargement...</p>
      </Centered>
    );
  }

  if (organizationContextStatus === "error") {
    return (
      <ErrorRetryScreen
        message={organizationContextError ?? "Une erreur est survenue."}
        onRetry={retryTenantContext}
        onReconnect={reconnect}
      />
    );
  }

  if (organizationContextStatus === "empty") {
    return (
      <Centered>
        <p className="max-w-sm text-sm text-slate-600">Aucune organisation ou école accessible avec ce compte.</p>
        <button type="button" onClick={reconnect} className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700">
          Se déconnecter
        </button>
      </Centered>
    );
  }

  if (organizationContextStatus === "selection-needed") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold text-slate-900">Choisissez une organisation</h1>
        <p className="max-w-sm text-sm text-slate-500">
          Votre compte est rattaché à plusieurs organisations. Sélectionnez celle avec laquelle vous
          souhaitez travailler.
        </p>
        <ul className="flex w-full max-w-sm flex-col gap-2">
          {availableOrganizations.map((organization) => (
            <li key={organization.id}>
              <button
                type="button"
                onClick={() => selectOrganization(organization.id)}
                className="w-full rounded border border-slate-300 px-4 py-2 text-left text-sm hover:bg-slate-100"
              >
                {organization.name}
              </button>
            </li>
          ))}
        </ul>
      </Centered>
    );
  }

  // organizationContextStatus === "resolved" à partir d'ici : passage au statut école.

  if (schoolContextStatus === "loading") {
    return (
      <Centered>
        <p className="text-sm text-slate-500">Chargement...</p>
      </Centered>
    );
  }

  if (schoolContextStatus === "error") {
    return (
      <ErrorRetryScreen
        message={schoolContextError ?? "Une erreur est survenue."}
        onRetry={retryTenantContext}
        onReconnect={reconnect}
      />
    );
  }

  if (schoolContextStatus === "empty") {
    return (
      <Centered>
        <p className="max-w-sm text-sm text-slate-600">Aucune organisation ou école accessible avec ce compte.</p>
        <button type="button" onClick={reconnect} className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700">
          Se déconnecter
        </button>
      </Centered>
    );
  }

  if (schoolContextStatus === "selection-needed") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold text-slate-900">Choisissez une école</h1>
        <p className="max-w-sm text-sm text-slate-500">
          Votre compte administre plusieurs écoles. Sélectionnez celle avec laquelle vous souhaitez
          travailler.
        </p>
        <ul className="flex w-full max-w-sm flex-col gap-2">
          {availableSchools.map((school) => (
            <li key={school.id}>
              <button
                type="button"
                onClick={() => selectSchool(school.id)}
                className="w-full rounded border border-slate-300 px-4 py-2 text-left text-sm hover:bg-slate-100"
              >
                {school.name}
              </button>
            </li>
          ))}
        </ul>
      </Centered>
    );
  }

  return <>{children}</>;
}
