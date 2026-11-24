"use client";

import { listPlatformOrganizations, type PlatformOrganization } from "@/lib/platform/client";
import { countryName } from "@/lib/geo/africanCountries";
import { formatDate, PlatformListPage } from "../PlatformListPage";

export default function PlatformOrganizationsPage() {
  return (
    <PlatformListPage<PlatformOrganization>
      title="Organisations"
      description="Toutes les organisations inscrites sur la plateforme (métadonnées uniquement)."
      fetchPage={listPlatformOrganizations}
      rowKey={(org) => org.id}
      columns={[
        { header: "Nom", render: (org) => org.name },
        { header: "Identifiant", render: (org) => org.slug },
        { header: "Pays", render: (org) => countryName(org.country_code) },
        { header: "Créée le", render: (org) => formatDate(org.created_at) },
      ]}
    />
  );
}
