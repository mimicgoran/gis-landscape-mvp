/**
 * Bootstrap frontend aplikacije.
 *
 * Phase 3 scope: mapa (Phase 1) + manual observer (Phase 2) + heading/FOV/
 * radius kontrole i viewing sector koji se crta i ažurira uživo na svaku
 * promjenu (Phase 3). Rezultati (Phase 9) i puni debug panel (Phase 11)
 * dolaze kasnije — vidi MVP backlog u
 * docs/architecture-feasibility-review.md, sekcija 13.
 *
 * Mapa zavisi od backenda (mora biti pokrenut i imati ARCGIS_CLIENT_ID/
 * SECRET podešene u .env) jer ArcGIS access token dolazi odatle — vidi
 * src/services/arcgisAuthService.js.
 */

import { createMapView } from "./map/mapSetup.js";
import { setupObserverInteraction } from "./map/observerInteraction.js";
import { renderSector } from "./map/sectorRenderer.js";
import { initControlsPanel } from "./ui/controlsPanel.js";
import { initDebugPanel } from "./ui/debugPanel.js";

async function bootstrap() {
  const statusBanner = document.getElementById("statusBanner");

  try {
    const { view, observerLayer, sectorLayer } = await createMapView("viewDiv");
    console.info("[main] MapView spreman.", view);

    const debugPanel = initDebugPanel();

    // Observer se drži ovdje (ne u kontrolama) jer ga postavlja klik na
    // mapu, ne slajder — sector renderer treba oba (observer + sector
    // parametre) na svaku promjenu bilo kog od njih.
    let currentObserver = null;

    const controls = initControlsPanel((sector) => {
      renderSector(sectorLayer, view, currentObserver, sector);
    });

    await setupObserverInteraction(view, observerLayer, (observer) => {
      currentObserver = observer;
      debugPanel.updateObserver(observer);
      renderSector(sectorLayer, view, currentObserver, controls.getSector());
      console.info("[main] Observer postavljen:", observer);
    });
  } catch (error) {
    console.error("[main] Neuspješna inicijalizacija mape:", error);
    statusBanner.hidden = false;
    statusBanner.textContent =
      "Greška pri učitavanju mape — provjeri da li je backend pokrenut " +
      "(uvicorn app.main:app) i da su ARCGIS_CLIENT_ID/SECRET podešeni u backend/.env. " +
      "Detalji u browser konzoli.";
  }
}

bootstrap();
