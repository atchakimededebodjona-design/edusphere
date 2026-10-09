"use client";

import { listPlatformSchools, type AcquisitionSource, type PlatformSchool } from "@/lib/platform/client";
import { formatDate, PlatformListPage } from "../PlatformListPage";

const SOURCE_LABELS: Record<AcquisitionSource, string> = {
  PLATFORM_OWNER: "Inscription directe",
  PARTNER: "Via un partenaire",
};

export default function PlatformSchoolsPage() {
  return (
    <PlatformListPage<PlatformSchool>
      title="Écoles"
      description="Toutes les écoles de la plateforme et leur source d'inscription (métadonnées uniquement)."
      fetchPage={listPlatformSchools}
      rowKey={(school) => school.id}
      columns={[
        { header: "Nom", render: (school) => school.name },
        { header: "Identifiant", render: (school) => school.slug },
        {
          header: "Source",
          render: (school) => (school.acquisition_source ? SOURCE_LABELS[school.acquisition_source] : "—"),
        },
        { header: "Créée le", render: (school) => formatDate(school.created_at) },
      ]}
    />
  );
}
