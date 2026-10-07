// "2015-03-18" -> "18/03/2015". Le backend renvoie toujours une date ISO ; un format inattendu
// reste affiché tel quel plutôt que de planter l'affichage.
export function formatDateFR(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : isoDate;
}
