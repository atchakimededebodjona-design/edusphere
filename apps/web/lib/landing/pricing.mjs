// Simulateur de prix de la page d'accueil : même calcul que l'API
// (apps/api/app/modules/subscriptions/pricing.py, `supplement_for` et service.price_for), à partir
// des montants publics de la grille active (`GET /api/v1/public/subscription-pricing`). Les bornes
// des tranches viennent de l'API, jamais de ce fichier.
//
// Module ES pur, sans dépendance : importé par la page (Next.js) et testé par
// lib/landing/pricing.test.mjs (`node --test`).

/**
 * @typedef {{ tier: number, min_students: number, max_students: number }} PublicTier
 * @typedef {{
 *   period_months: number,
 *   base_amount: string,
 *   supplement_tier_1: string,
 *   supplement_tier_2: string,
 *   supplement_tier_3: string,
 *   supplement_tier_4: string | null,
 *   supplement_step: string | null,
 * }} PublicPeriod
 * @typedef {{ currency: string, tiers: PublicTier[], step_students: number, periods: PublicPeriod[] }} PublicPricing
 */

/** @param {string | null | undefined} value */
function amount(value) {
  if (value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/**
 * Supplément d'une durée pour cet effectif, ou null si la grille ne le chiffre pas (la facture
 * passerait alors en devis).
 * @param {PublicPricing} pricing
 * @param {PublicPeriod} period
 * @param {number} studentCount
 * @returns {number | null}
 */
function supplementFor(pricing, period, studentCount) {
  const tier = pricing.tiers.find((t) => t.min_students <= studentCount && studentCount <= t.max_students);
  if (tier) {
    if (tier.tier === 0) return 0;
    return amount(/** @type {Record<string, string | null>} */ (period)[`supplement_tier_${tier.tier}`]);
  }
  const last = pricing.tiers[pricing.tiers.length - 1];
  const lastSupplement = amount(/** @type {Record<string, string | null>} */ (period)[`supplement_tier_${last.tier}`]);
  const perStep = amount(period.supplement_step);
  if (lastSupplement === null || perStep === null) return null;
  const steps = Math.ceil((studentCount - last.max_students) / pricing.step_students);
  return lastSupplement + steps * perStep;
}

/**
 * Prix total d'une durée pour cet effectif, ou null (devis, durée absente de la grille, effectif
 * invalide).
 * @param {PublicPricing | null} pricing
 * @param {number} periodMonths
 * @param {number} studentCount
 * @returns {number | null}
 */
export function priceFor(pricing, periodMonths, studentCount) {
  if (!pricing || !Number.isInteger(studentCount) || studentCount < 0) return null;
  const period = pricing.periods.find((p) => p.period_months === periodMonths);
  if (!period) return null;
  const base = amount(period.base_amount);
  const supplement = supplementFor(pricing, period, studentCount);
  return base === null || supplement === null ? null : base + supplement;
}

/**
 * Économie d'une durée par rapport au même nombre de trimestres payés un par un, en % entier
 * (5 pour 57 000 contre 2 × 30 000). 0 s'il n'y en a pas.
 * @param {number | null} price
 * @param {number | null} quarterlyPrice
 * @param {number} periodMonths
 * @returns {number}
 */
export function savingsPercent(price, quarterlyPrice, periodMonths) {
  if (price === null || quarterlyPrice === null || quarterlyPrice <= 0) return 0;
  const reference = quarterlyPrice * (periodMonths / 3);
  const saving = Math.round(((reference - price) / reference) * 100);
  return saving > 0 ? saving : 0;
}

/**
 * « 30 000 FCFA » (espace fine insécable entre les milliers, comme le reste de l'application).
 * @param {number} value
 * @returns {string}
 */
export function formatFcfa(value) {
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(value)} FCFA`;
}
