/**
 * Prikazuje rezultate analize (tačkasti i area feature-i) -- originalni
 * brief Phase 9 ("Visible/blocked UI", sekcija 35), uradeno zajedno sa
 * Phase 10 (vidi glavnu arhitekturu, napomena o procjepu u numeraciji faza).
 *
 * Namjerno prost DOM (liste, ne tabela/framework) -- brief tačka 35: "Nemoj
 * praviti komplikovan UI framework samo zbog ovoga."
 *
 * Dizajn prilagođen nakon prvog pravog telefon testa (korisnička odluka,
 * vidi docs/architecture-feasibility-review.md, sekcija 33):
 * - JEDNA ravna lista, bez "Tačke"/"Rijeke i vode" sekcija -- korisnik je
 *   ocijenio da odvojene sekcije nisu potrebne za jedan pogled u sektor.
 * - Svaki red pokazuje SAMO ime i kategoriju (jednom) -- distance/bearing/
 *   procenat vidljivosti su namjerno uklonjeni iz liste (bili su duplirani
 *   sa VIDLJIVO/DJELIMIČNO/ZAKLONJENO bedžom, koji već nosi tu informaciju
 *   na jednostavniji, skalabilniji način). Puni brojevi i dalje postoje u
 *   `analysis` objektu i debug panelu za onoga kome trebaju.
 * - Feature bez imena (npr. bezimeni `natural=water` poligon koji OSM
 *   mapiranje ostavi odvojen od imenovane rijeke i pored merge fix-a iz
 *   Phase 10 -- vidi arhitekturu sekcija 30) se NE prikazuje -- korisnička
 *   odluka: neimenovan objekat nije korisna informacija planinaru.
 * - Ekavica (Reka/DELIMIČNO), ne ijekavica -- korisnička odluka.
 *
 * AI opis (Phase 13) NIJE ovdje -- ovaj panel prikazuje samo strukturirane
 * GIS rezultate, po dizajnu "GEOSPATIAL ANALYSIS FIRST, AI SECOND" (brief
 * sekcija 7).
 */

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

// Badge tekst i sortirajući prioritet (niže = prikazuje se prije) --
// visible mora biti vizuelno najistaknutiji/prvi (brief tačka 35).
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
 * JEDNU listu jednoobraznih redova, izbacuje neimenovane feature-e, i
 * sortira: visible prvo, zatim partially_visible, zatim blocked (brief
 * tačka 35); unutar iste grupe, bliži prvo.
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

  return rows
    .filter((row) => row.name) // bez imena -- ne prikazuj (korisnička odluka)
    .sort((a, b) => VISIBILITY_RANK[a.visibility] - VISIBILITY_RANK[b.visibility] || a.distanceKm - b.distanceKm);
}

function pointFeatureToRow(feature, visibility) {
  return {
    name: feature.name,
    categoryLabel: POINT_CATEGORY_LABELS[feature.category] ?? feature.category,
    visibility,
    distanceKm: feature.distance_km,
  };
}

function areaFeatureToRow(feature) {
  return {
    name: feature.name,
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
