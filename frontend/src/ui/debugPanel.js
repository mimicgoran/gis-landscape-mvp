/**
 * Debug panel — Phase 2 scope: prikazuje koordinate postavljenog observera.
 *
 * Namjerno minimalno (samo lat/lon) u ovoj fazi. Kasnije faze dopisuju u
 * isti panel: FOV/radius/heading (Phase 3), broj OSM kandidata (Phase 4/5),
 * location quality — GPS accuracy, DEM elevation, elevation_source (Phase 7)
 * — vidi docs/architecture-feasibility-review.md, sekcija 15/57 originalnog
 * brifa. Ne pravimo poseban UI framework za ovo (brief, tačka 57: "Ne treba
 * production observability stack. Jednostavan debug panel je dovoljan.").
 */

const PLACEHOLDER_TEXT = "Klikni na mapu da postaviš observer.";

/**
 * Inicijalizuje debug panel i vraća objekat sa metodama za ažuriranje.
 *
 * @returns {{ updateObserver: (observer: { latitude: number, longitude: number }) => void }}
 */
export function initDebugPanel() {
  const panel = document.getElementById("debugPanel");
  if (!panel) {
    throw new Error("initDebugPanel: element #debugPanel ne postoji u DOM-u (provjeri index.html).");
  }
  panel.textContent = PLACEHOLDER_TEXT;

  return {
    updateObserver(observer) {
      panel.replaceChildren();

      const title = document.createElement("strong");
      title.textContent = "Observer";

      const coords = document.createElement("div");
      coords.textContent = `lat: ${observer.latitude.toFixed(6)}, lon: ${observer.longitude.toFixed(6)}`;

      panel.append(title, coords);
    },
  };
}
