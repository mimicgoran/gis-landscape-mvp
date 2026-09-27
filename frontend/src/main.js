/**
 * Bootstrap frontend aplikacije.
 *
 * Phase 2 scope: mapa (Phase 1) + manual observer (klik na mapu postavlja
 * marker) + minimalan debug panel sa koordinatama. Kontrole (heading/FOV/
 * radius), rezultati i puni debug panel dolaze u kasnijim fazama (vidi MVP
 * backlog u docs/architecture-feasibility-review.md, sekcija 13).
 *
 * Mapa zavisi od backenda (mora biti pokrenut i imati ARCGIS_CLIENT_ID/
 * SECRET podešene u .env) jer ArcGIS access token dolazi odatle — vidi
 * src/services/arcgisAuthService.js.
 */

import { createMapView } from "./map/mapSetup.js";
import { setupObserverInteraction } from "./map/observerInteraction.js";
import { initDebugPanel } from "./ui/debugPanel.js";

async function bootstrap() {
  const statusBanner = document.getElementById("statusBanner");

  try {
    const { view, observerLayer } = await createMapView("viewDiv");
    console.info("[main] MapView spreman.", view);

    const debugPanel = initDebugPanel();

    await setupObserverInteraction(view, observerLayer, (observer) => {
      debugPanel.updateObserver(observer);
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
