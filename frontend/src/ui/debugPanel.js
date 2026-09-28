/**
 * Debug / location-quality panel.
 *
 * Phase 2 je pokazivao samo observer lat/lon. Backend je od Phase 7 nadalje
 * vraćao pun `location_quality` blok i `debug` brojače (brief tačka 15/57),
 * ali frontend ih do sada nije prikazivao -- ovo je taj nedostajući dio,
 * uraden zajedno sa Phase 10 (vidi glavnu arhitekturu, napomena o procjepu
 * u numeraciji faza).
 *
 * Kolabsiran po defaultu (brief sekcija 15: "Ne želim zatrpati glavni UI
 * tehničkim informacijama... mali expandable/debug/info panel") -- prikazuje
 * samo jednu liniju sažetka dok se ne raželi (klik na strelicu).
 */

const PLACEHOLDER_TEXT = "Klikni na mapu ili koristi dugme 'Koristi moju lokaciju' da postaviš observer.";

const CONFIDENCE_LABELS = { high: "HIGH", medium: "MEDIUM", low: "LOW" };

/**
 * @returns {{
 *   updateObserver: (observer: { latitude: number, longitude: number, horizontalAccuracyM?: number|null, phoneAltitudeM?: number|null, phoneAltitudeAccuracyM?: number|null }) => void,
 *   updateAnalysis: (analysis: object) => void,
 * }}
 */
export function initDebugPanel() {
  const panel = document.getElementById("debugPanel");
  if (!panel) {
    throw new Error("initDebugPanel: element #debugPanel ne postoji u DOM-u (provjeri index.html).");
  }
  panel.textContent = PLACEHOLDER_TEXT;

  let expanded = false;

  function renderPanel(summaryText, detailRows) {
    panel.replaceChildren();

    const header = document.createElement("div");
    header.className = "debug-panel-header";

    const summary = document.createElement("strong");
    summary.textContent = summaryText;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "debug-panel-toggle";
    toggle.setAttribute("aria-label", "Prikaži/sakrij detalje");
    toggle.textContent = expanded ? "▲" : "▼";

    const details = document.createElement("div");
    details.className = "debug-panel-details";
    details.hidden = !expanded;
    detailRows.forEach(([label, value]) => {
      const row = document.createElement("div");
      row.className = "debug-panel-row";
      row.textContent = `${label}: ${value}`;
      details.append(row);
    });

    toggle.addEventListener("click", () => {
      expanded = !expanded;
      details.hidden = !expanded;
      toggle.textContent = expanded ? "▲" : "▼";
    });

    header.append(summary, toggle);
    panel.append(header, details);
  }

  return {
    // Poziva se odmah nakon postavljanja observera (klik ili geolocation),
    // PRIJE nego što je analiza pokrenuta -- sirovi podaci, bez location
    // quality (taj dolazi samo iz analyze odgovora, vidi updateAnalysis).
    updateObserver(observer) {
      const rows = [
        ["Latitude", observer.latitude.toFixed(6)],
        ["Longitude", observer.longitude.toFixed(6)],
      ];
      if (observer.horizontalAccuracyM != null) {
        rows.push(["GPS accuracy", `± ${observer.horizontalAccuracyM.toFixed(0)} m`]);
      }
      if (observer.phoneAltitudeM != null) {
        rows.push(["Phone altitude", `${observer.phoneAltitudeM.toFixed(0)} m`]);
      }
      if (observer.phoneAltitudeAccuracyM != null) {
        rows.push(["Phone altitude accuracy", `± ${observer.phoneAltitudeAccuracyM.toFixed(0)} m`]);
      }
      renderPanel(`Observer: ${observer.latitude.toFixed(5)}, ${observer.longitude.toFixed(5)}`, rows);
    },

    // Poziva se nakon uspješnog /api/v1/analyze/preview odgovora -- pun
    // location_quality + debug prikaz (brief sekcija 57: skoro sva polja
    // otuda su već dostupna u backend odgovoru, samo do sada nisu bila
    // prikazana na frontendu).
    updateAnalysis(analysis) {
      const { observer, location_quality: lq, debug } = analysis;
      const confidenceLabel = lq?.confidence ? CONFIDENCE_LABELS[lq.confidence] ?? lq.confidence : "N/A";

      renderPanel(`Location quality: ${confidenceLabel}`, [
        ["Latitude", observer.latitude.toFixed(6)],
        ["Longitude", observer.longitude.toFixed(6)],
        [
          "GPS accuracy",
          lq?.horizontal_accuracy_m != null ? `± ${lq.horizontal_accuracy_m.toFixed(0)} m` : "N/A (ručni observer)",
        ],
        ["Phone altitude", lq?.phone_altitude_m != null ? `${lq.phone_altitude_m.toFixed(0)} m` : "N/A"],
        [
          "Phone altitude accuracy",
          lq?.phone_altitude_accuracy_m != null ? `± ${lq.phone_altitude_accuracy_m.toFixed(0)} m` : "N/A",
        ],
        ["DEM elevation", lq?.dem_elevation_m != null ? `${lq.dem_elevation_m.toFixed(0)} m` : "N/A"],
        [
          "Observer elevation",
          observer.observer_elevation_m != null ? `${observer.observer_elevation_m.toFixed(1)} m` : "N/A",
        ],
        ["Elevation source", lq?.elevation_source ?? "N/A"],
        ["Heading", `${observer.heading_deg}°`],
        ["FOV", `${observer.fov_deg}°`],
        ["Radius", `${observer.radius_km} km`],
        ["OSM kandidata (ukupno)", debug?.osm_candidates_total ?? "N/A"],
        ["Nakon FOV/radius filtera", debug?.candidates_after_fov_radius_filter ?? "N/A"],
        ["Analizirano", debug?.candidates_analyzed ?? "N/A"],
        ["Vidljivo", debug?.visible_count ?? "N/A"],
        ["Zaklonjeno", debug?.blocked_count ?? "N/A"],
        ["Area feature-i (ukupno)", debug?.area_features_total ?? "N/A"],
        ["Area feature-i u sektoru", debug?.area_features_in_sector ?? "N/A"],
      ]);
    },
  };
}
