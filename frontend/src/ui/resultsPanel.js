/**
 * Prikazuje rezultate analize (visible/blocked tačkasti feature-i i area
 * feature-i) -- originalni brief Phase 9 ("Visible/blocked UI", sekcija 35),
 * uradeno tek sada zajedno sa Phase 10 (vidi glavnu arhitekturu, napomena
 * o procjepu u numeraciji faza).
 *
 * Namjerno prost DOM (liste, ne tabela/framework) -- brief tačka 35: "Nemoj
 * praviti komplikovan UI framework samo zbog ovoga." Vizuelni naglasak na
 * visible feature-ima (zelena značka, isticanje) nad blocked (sivkasto,
 * manje upadljivo) -- isto tačka 35.
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
  river: "Rijeka",
  water: "Vodena površina",
  park: "Park",
  national_park: "Nacionalni park",
};

const AREA_VISIBILITY_LABELS = {
  visible: "VIDLJIVO",
  partially_visible: "DJELIMIČNO",
  blocked: "ZAKLONJENO",
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

      const totalPointFeatures = analysis.visible_features.length + analysis.blocked_features.length;

      if (totalPointFeatures === 0 && analysis.area_features.length === 0) {
        panel.append(el("div", { className: "results-status" }, "Nema identifikovanih objekata u ovom sektoru."));
        return;
      }

      if (totalPointFeatures > 0) {
        panel.append(el("h3", { className: "results-heading" }, "Tačke"));
        // Visible prvo -- vizuelno važniji od blocked (brief tačka 35).
        for (const feature of analysis.visible_features) {
          panel.append(renderPointFeatureRow(feature));
        }
        for (const feature of analysis.blocked_features) {
          panel.append(renderPointFeatureRow(feature));
        }
      }

      if (analysis.area_features.length > 0) {
        panel.append(el("h3", { className: "results-heading" }, "Rijeke / vode / parkovi"));
        for (const feature of analysis.area_features) {
          panel.append(renderAreaFeatureRow(feature));
        }
      }
    },
  };
}

function renderPointFeatureRow(feature) {
  const isVisible = feature.visibility === "visible";

  const info = el("div", { className: "result-row-info" });
  info.append(
    el("div", { className: "result-row-name" }, feature.name ?? POINT_CATEGORY_LABELS[feature.category] ?? feature.category),
    el(
      "div",
      { className: "result-row-meta" },
      `${POINT_CATEGORY_LABELS[feature.category] ?? feature.category} · ${feature.distance_km.toFixed(1)} km · ` +
        `${Math.round(feature.bearing_deg)}° · ${Math.round(feature.elevation_m)} m`
    )
  );

  const row = el("div", { className: `result-row ${isVisible ? "result-row-visible" : "result-row-blocked"}` });
  row.append(info, el("div", { className: `result-badge ${isVisible ? "result-badge-visible" : "result-badge-blocked"}` }, isVisible ? "VIDLJIVO" : "ZAKLONJENO"));
  return row;
}

function renderAreaFeatureRow(feature) {
  const isVisible = feature.visibility === "visible";
  const isPartial = feature.visibility === "partially_visible";
  const badgeClass = isVisible ? "result-badge-visible" : isPartial ? "result-badge-partial" : "result-badge-blocked";
  const rowClass = isVisible ? "result-row-visible" : isPartial ? "result-row-partial" : "result-row-blocked";

  const info = el("div", { className: "result-row-info" });
  info.append(
    el("div", { className: "result-row-name" }, feature.name ?? AREA_CATEGORY_LABELS[feature.category] ?? feature.category),
    el(
      "div",
      { className: "result-row-meta" },
      `${AREA_CATEGORY_LABELS[feature.category] ?? feature.category} · ${feature.closest_distance_km.toFixed(1)} km · ` +
        `${Math.round(feature.bearing_deg)}° · ${Math.round(feature.visible_fraction * 100)}% vidljivo`
    )
  );

  const row = el("div", { className: `result-row ${rowClass}` });
  row.append(info, el("div", { className: `result-badge ${badgeClass}` }, AREA_VISIBILITY_LABELS[feature.visibility]));
  return row;
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
