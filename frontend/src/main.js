/**
 * Bootstrap frontend aplikacije.
 *
 * Phase 1 scope: montirati mapu, ništa više. Kontrole, observer, sektor i
 * rezultati dolaze u kasnijim fazama (vidi MVP backlog u
 * docs/architecture-feasibility-review.md, sekcija 13) — layeri za njih se
 * već kreiraju u mapSetup.js da naredne faze samo dopisuju logiku bez
 * refaktorisanja osnove.
 *
 * Mapa zavisi od backenda (mora biti pokrenut i imati ARCGIS_CLIENT_ID/
 * SECRET podešene u .env) jer ArcGIS access token dolazi odatle — vidi
 * src/services/arcgisAuthService.js.
 */

import { createMapView } from "./map/mapSetup.js";

async function bootstrap() {
  const statusBanner = document.getElementById("statusBanner");

  try {
    const { view } = await createMapView("viewDiv");
    console.info("[main] MapView spreman.", view);
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
