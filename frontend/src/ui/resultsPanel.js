/**
 * Prikazuje rezultate analize (tačkasti i area feature-i) -- originalni
 * brief Phase 9 ("Visible/blocked UI", sekcija 35), uradeno zajedno sa
 * Phase 10 (vidi glavnu arhitekturu, napomena o procjepu u numeraciji faza).
 *
 * Namjerno prost DOM (liste, ne tabela/framework) -- brief tačka 35: "Nemoj
 * praviti komplikovan UI framework samo zbog ovoga."
 *
 * Dizajn prilagođen nakon prvog i drugog pravog telefon testa (korisnička
 * odluka, vidi docs/architecture-feasibility-review.md, sekcija 33):
 * - JEDNA ravna lista, bez "Tačke"/"Rijeke i vode" sekcija.
 * - Svaki red pokazuje SAMO ime i kategoriju (jednom) -- distance/bearing/
 *   procenat vidljivosti su namjerno uklonjeni (bili su duplirani sa
 *   VIDLJIVO/DELIMIČNO/ZAKLONJENO bedžom).
 * - Feature bez imena se ne prikazuje. Feature čije je ime IDENTIČNO
 *   generičkoj kategoriji (npr. OSM `name=Vodena površina` -- stvaran
 *   slučaj, ne pretpostavka, nađen u drugom telefon testu) se tretira kao
 *   da nema pravo ime -- takođe se ne prikazuje.
 * - Feature-i istog imena se spajaju u JEDAN red (npr. Dunav se u OSM-u
 *   često sastoji od više odvojenih `way` segmenata sa istim `name` tagom,
 *   svaki sa svojom vlastitom vidljivošću) -- prikazuje se najbolja
 *   (najvidljivija) vrijednost među duplikatima, ne svaki segment posebno.
 * - Ćirilična OSM imena (npr. "Дунав") se transliterišu u latinicu
 *   (`utils/text.js`) da se ne mješaju dva pisma u istoj listi -- kategorije
 *   i bedževi su već na latinici.
 * - Ekavica (Reka/DELIMIČNO), ne ijekavica.
 *
 * AI opis (Phase 13) NIJE ovdje -- ovaj panel prikazuje samo strukturirane
 * GIS rezultate, po dizajnu "GEOSPATIAL ANALYSIS FIRST, AI SECOND" (brief
 * sekcija 7).
 */

import { cyrillicToLatin } from "../utils/text.js";

const POINT_CATEGORY_LABELS = {
  peak: "Vrh",
  settlement: "Naselje",
  viewpoint: "Vidikovac",
};

const AREA_CATEGORY_LABELS = {
  river: "Reka",
  water: "Vodena površina",
  park: "Park",
  national_park: "Nacionalni park",
};

// Badge tekst i sortirajući prioritet (niže = prikazuje se prije / smatra
// se "boljim" kad se spajaju duplikati istog imena) -- visible mora biti
// vizuelno najistaknutiji/prvi (brief tačka 35).
const VISIBILITY_RANK = { visible: 0, partially_visible: 1, blocked: 2 };
const VISIBILITY_BADGE_LABELS = {
  visible: "VIDLJIVO",
  partially_visible: "DELIMIČNO",
  blocked: "ZAKLONJENO",
};
const VISIBILITY_BADGE_CLASS = {
  visible: "result-badge-visible",
  partially_visible: "result-badge-partial",
  blocked: "result-badge-blocked",
};
const VISIBILITY_ROW_CLASS = {
  visible: "result-row-visible",
  partially_visible: "result-row-partial",
  blocked: "result-row-blocked",
};

/**
 * @returns {{
 *   showLoading: () => void,
 *   showError: (message: string) => void,
 *   hide: () => void,
 *   render: (analysis: object) => void,
 * }}
 */
export function initResultsPanel() {
  const panel = document.getElementById("resultsPanel");
  if (!panel) {
    throw new Error("initResultsPanel: element #resultsPanel ne postoji u DOM-u (provjeri index.html).");
  }

  return {
    showLoading() {
      panel.hidden = false;
      panel.replaceChildren(el("div", { className: "results-status" }, "Analiziram…"));
    },

    showError(message) {
      panel.hidden = false;
      panel.replaceChildren(el("div", { className: "results-status results-status-error" }, message));
    },

    hide() {
      panel.hidden = true;
      panel.replaceChildren();
    },

    render(analysis) {
      panel.hidden = false;
      panel.replaceChildren();

      const rows = buildRows(analysis);

      if (rows.length === 0) {
        panel.append(el("div", { className: "results-status" }, "Nema identifikovanih objekata u ovom sektoru."));
        return;
      }

      for (const row of rows) {
        panel.append(renderRow(row));
      }
    },
  };
}

/**
 * Spaja tačkaste (visible_features + blocked_features) i area feature-e u
 * JEDNU listu jednoobraznih redova:
 * 1. izbacuje feature-e bez pravog imena (nema imena, ili je ime identično
 *    generičkoj kategoriji -- vidi modul docstring),
 * 2. spaja duplikate istog imena u jedan red (najbolja vidljivost, najbliža
 *    distanca -- vidi `mergeDuplicateNames`),
 * 3. sortira: visible prvo, zatim partially_visible, zatim blocked (brief
 *    tačka 35); unutar iste grupe, bliži prvo.
 */
function buildRows(analysis) {
  const rows = [];

  for (const feature of analysis.visible_features) {
    rows.push(pointFeatureToRow(feature, "visible"));
  }
  for (const feature of analysis.blocked_features) {
    rows.push(pointFeatureToRow(feature, "blocked"));
  }
  for (const feature of analysis.area_features) {
    rows.push(areaFeatureToRow(feature));
  }

  const named = rows.filter((row) => row.name && row.name !== row.categoryLabel);

  return mergeDuplicateNames(named).sort(
    (a, b) => VISIBILITY_RANK[a.visibility] - VISIBILITY_RANK[b.visibility] || a.distanceKm - b.distanceKm
  );
}

/**
 * Grupiše redove po (ime, kategorija) paru -- ista imena u različitim
 * kategorijama (npr. selo i rijeka sa istim imenom) se namjerno NE spajaju,
 * to bi bilo pogrešno. Za svaku grupu bira najbolju (najnižu rank) vidljivost
 * i najmanju distancu među duplikatima -- "ako je vidljivo makar jednom,
 * tretiraj ga kao vidljivo, ne prikazuj dva puta" (korisnička odluka).
 */
function mergeDuplicateNames(rows) {
  const byKey = new Map();

  for (const row of rows) {
    const key = `${row.name}\u0000${row.categoryLabel}`;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, { ...row });
      continue;
    }
    if (VISIBILITY_RANK[row.visibility] < VISIBILITY_RANK[existing.visibility]) {
      existing.visibility = row.visibility;
    }
    existing.distanceKm = Math.min(existing.distanceKm, row.distanceKm);
  }

  return Array.from(byKey.values());
}

function pointFeatureToRow(feature, visibility) {
  return {
    name: cyrillicToLatin(feature.name),
    categoryLabel: POINT_CATEGORY_LABELS[feature.category] ?? feature.category,
    visibility,
    distanceKm: feature.distance_km,
  };
}

function areaFeatureToRow(feature) {
  return {
    name: cyrillicToLatin(feature.name),
    categoryLabel: AREA_CATEGORY_LABELS[feature.category] ?? feature.category,
    visibility: feature.visibility,
    distanceKm: feature.closest_distance_km,
  };
}

function renderRow(row) {
  const info = el("div", { className: "result-row-info" });
  info.append(el("div", { className: "result-row-name" }, row.name), el("div", { className: "result-row-meta" }, row.categoryLabel));

  const element = el("div", { className: `result-row ${VISIBILITY_ROW_CLASS[row.visibility]}` });
  element.append(info, el("div", { className: `result-badge ${VISIBILITY_BADGE_CLASS[row.visibility]}` }, VISIBILITY_BADGE_LABELS[row.visibility]));
  return element;
}

function el(tag, props, text) {
  const element = document.createElement(tag);
  if (props) {
    Object.assign(element, props);
  }
  if (text != null) {
    element.textContent = text;
  }
  return element;
}
