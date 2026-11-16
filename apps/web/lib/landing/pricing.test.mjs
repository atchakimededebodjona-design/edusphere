// Tests du simulateur de prix de la page d'accueil (`node --test`). Les attentes reprennent les
// règles de l'API (apps/api/tests/test_subscriptions_pricing.py) sur la grille HT du 2026-11-15.
import assert from "node:assert/strict";
import { test } from "node:test";
import { formatFcfa, priceFor, savingsPercent } from "./pricing.mjs";

const TIERS = [
  { tier: 0, min_students: 0, max_students: 100 },
  { tier: 1, min_students: 101, max_students: 250 },
  { tier: 2, min_students: 251, max_students: 500 },
  { tier: 3, min_students: 501, max_students: 750 },
  { tier: 4, min_students: 751, max_students: 1000 },
];

function period(months, base, s1, s2, s3, s4, step) {
  return {
    period_months: months,
    base_amount: `${base}.00`,
    supplement_tier_1: `${s1}.00`,
    supplement_tier_2: `${s2}.00`,
    supplement_tier_3: `${s3}.00`,
    supplement_tier_4: s4 === null ? null : `${s4}.00`,
    supplement_step: step === null ? null : `${step}.00`,
  };
}

const GRID = {
  currency: "XOF",
  tiers: TIERS,
  step_students: 250,
  periods: [
    period(3, 30000, 10000, 25000, 45000, 70000, 25000),
    period(6, 57000, 19000, 47500, 85500, 133000, 47500),
    period(12, 108000, 36000, 90000, 162000, 252000, 90000),
  ],
};

test("forfait de base jusqu'à 100 élèves, y compris sans élève", () => {
  assert.equal(priceFor(GRID, 3, 0), 30000);
  assert.equal(priceFor(GRID, 3, 100), 30000);
  assert.equal(priceFor(GRID, 12, 15), 108000);
});

test("bornes des tranches", () => {
  assert.equal(priceFor(GRID, 3, 101), 40000);
  assert.equal(priceFor(GRID, 3, 250), 40000);
  assert.equal(priceFor(GRID, 3, 251), 55000);
  assert.equal(priceFor(GRID, 6, 750), 57000 + 85500);
  assert.equal(priceFor(GRID, 3, 751), 100000);
  assert.equal(priceFor(GRID, 3, 1000), 100000);
});

test("au-delà de 1 000 élèves : un supplément par palier de 250 élèves commencé", () => {
  assert.equal(priceFor(GRID, 3, 1001), 30000 + 70000 + 25000);
  assert.equal(priceFor(GRID, 3, 1250), 30000 + 70000 + 25000);
  assert.equal(priceFor(GRID, 3, 1251), 30000 + 70000 + 2 * 25000);
  assert.equal(priceFor(GRID, 12, 1300), 108000 + 252000 + 2 * 90000);
});

test("sans palier ni tranche 751-1000 : devis (null), comme l'API", () => {
  const noStep = { ...GRID, periods: [period(3, 30000, 10000, 25000, 45000, 70000, null)] };
  assert.equal(priceFor(noStep, 3, 1001), null);
  assert.equal(priceFor(noStep, 3, 1000), 100000);
  const oldGrid = { ...GRID, periods: [period(3, 30000, 10000, 25000, 45000, null, null)] };
  assert.equal(priceFor(oldGrid, 3, 800), null);
  assert.equal(priceFor(oldGrid, 3, 600), 75000);
});

test("entrées invalides et grille absente", () => {
  assert.equal(priceFor(null, 3, 10), null);
  assert.equal(priceFor(GRID, 9, 10), null);
  assert.equal(priceFor(GRID, 3, -1), null);
  assert.equal(priceFor(GRID, 3, 12.5), null);
});

test("économie des durées longues par rapport aux trimestres", () => {
  assert.equal(savingsPercent(57000, 30000, 6), 5);
  assert.equal(savingsPercent(108000, 30000, 12), 10);
  assert.equal(savingsPercent(30000, 30000, 3), 0);
  assert.equal(savingsPercent(null, 30000, 6), 0);
});

test("format des montants", () => {
  assert.match(formatFcfa(30000), /^30\s000 FCFA$/u);
  assert.match(formatFcfa(108000), /^108\s000 FCFA$/u);
});
