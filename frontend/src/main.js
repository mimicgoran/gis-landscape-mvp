/**
 * Bootstrap frontend aplikacije.
 *
 * Ovaj fajl je do sada bio na nivou originalnog Phase 3 scope-a (mapa +
 * manual observer + heading/FOV/radius kontrole + sektor koji se crta
 * uzživo) -- rezultati (originalni brief Phase 9 "Visible/blocked UI") i
 * mobile geolocation (Phase 10) nikad nisu bili povezani na frontend-u,
 * iako je backend za oboje odavno gotov i testiran. Ova verzija dodaje oba
 * zajedno (vidi glavnu arhitekturu, napomena o procjepu u numeraciji faza
 * -- backend "Phase 9" je hronološki postao nešto drugo, area feature
 * scope expansion, pa je originalni frontend Phase 9 tiho preskocen do sada).
 *
 * Mapa zavisi od backenda (mora biti pokrenut i imati ARCGIS_CLIENT_ID/
 * SECRET podesene u .env) jer ArcGIS access token dolazi odatle -- vidi
 * src/services/arcgisAuthService.js. Analiza ("Šta gledam?") i geolocation
 * takode zavise od backenda -- vidi src/services/analyzeService.js i
 * src/services/geolocationService.js.
 */

import { createMapView } from "./map/mapSetup.js";
import { setupObserverInteraction, placeObserverMarker } from "./map/observerInteraction.js";
import { renderSector } from "./map/sectorRenderer.js";
import { renderResults } from "./map/resultsRenderer.js";
import { initControlsPanel } from "./ui/controlsPanel.js";
import { initDebugPanel } from "./ui/debugPanel.js";
import { initResultsPanel } from "./ui/resultsPanel.js";
import { initActionButtons } from "./ui/actionButtons.js";
import { getCurrentPosition } from "./services/geolocationService.js";
import { fetchAnalysis } from "./services/analyzeService.js";

async function bootstrap() {
  const statusBanner = document.getElementById("statusBanner");

  function showBanner(message) {
    statusBanner.hidden = false;
    statusBanner.textContent = message;
  }
  function hideBanner() {
    statusBanner.hidden = true;
  }

  try {
    const { view, observerLayer, sectorLayer, resultsLayer } = await createMapView("viewDiv");
    console.info("[main] MapView spreman.", view);

    const debugPanel = initDebugPanel();
    const resultsPanel = initResultsPanel();

    // Observer se drži ovdje (ne u kontrolama) jer ga postavlja klik na
    // mapu ILI geolocation, ne slajder -- sector renderer i analyze poziv
    // trebaju i observer i sector parametre na svaku promjenu bilo kog od
    // njih. Za manual klik, horizontalAccuracyM/phoneAltitudeM/
    // phoneAltitudeAccuracyM ostaju undefined (backend ih tretira isto kao
    // `null` -- vidi ObserverInput model).
    let currentObserver = null;

    function clearStaleResults() {
      // Rezultati važe za observer poziciju u trenutku poziva -- kad se
      // observer pomjeri (novi klik ili nova geolocation), stari rezultati
      // više ne odgovaraju novoj poziciji, pa se sklanjaju umjesto da
      // zavaravajuće ostanu na mapi/panelu dok se "Šta gledam?" ponovo ne
      // pritisne.
      resultsLayer.removeAll();
      resultsPanel.hide();
    }

    const controls = initControlsPanel((sector) => {
      renderSector(sectorLayer, view, currentObserver, sector);
    });

    const actions = initActionButtons({
      onLocate: async () => {
        hideBanner();
        actions.setLocateLoading(true);
        try {
          const position = await getCurrentPosition();
          await placeObserverMarker(view, observerLayer, position.latitude, position.longitude);
          currentObserver = position;
          debugPanel.updateObserver(position);
          renderSector(sectorLayer, view, currentObserver, controls.getSector());
          clearStaleResults();
          // Rekentriranje samo za geolocation (ne i manual klik -- tamo je
          // korisnik već gledao tačno tu tačku na mapi).
          view.goTo({ center: [position.longitude, position.latitude], zoom: 13 }).catch(() => {});
          console.info("[main] Observer postavljen preko geolocation-a:", position);
        } catch (error) {
          console.warn("[main] Geolocation nije uspio:", error);
          showBanner(error.message);
        } finally {
          actions.setLocateLoading(false);
        }
      },

      onAnalyze: async () => {
        if (!currentObserver) {
          showBanner("Prvo postavi observera -- klikni na mapu ili koristi dugme 'Koristi moju lokaciju'.");
          return;
        }

        hideBanner();
        actions.setAnalyzeLoading(true);
        resultsPanel.showLoading();

        try {
          const sector = controls.getSector();
          const analysis = await fetchAnalysis({
            latitude: currentObserver.latitude,
            longitude: currentObserver.longitude,
            headingDeg: sector.headingDeg,
            fovDeg: sector.fovDeg,
            radiusKm: sector.radiusKm,
            horizontalAccuracyM: currentObserver.horizontalAccuracyM,
            phoneAltitudeM: currentObserver.phoneAltitudeM,
            phoneAltitudeAccuracyM: currentObserver.phoneAltitudeAccuracyM,
          });

          debugPanel.updateAnalysis(analysis);
          resultsPanel.render(analysis);
          await renderResults(resultsLayer, analysis);
          console.info("[main] Analiza završena:", analysis.debug);
        } catch (error) {
          console.error("[main] Analiza nije uspjela:", error);
          resultsPanel.showError(error.message);
          showBanner(error.message);
        } finally {
          actions.setAnalyzeLoading(false);
        }
      },
    });

    await setupObserverInteraction(view, observerLayer, (observer) => {
      // Manual klik -- accuracy/altitude polja namjerno izostavljena
      // (undefined), fetchAnalysis ih onda ne šalje backend-u uopšte.
      currentObserver = observer;
      debugPanel.updateObserver(observer);
      renderSector(sectorLayer, view, currentObserver, controls.getSector());
      clearStaleResults();
      console.info("[main] Observer postavljen klikom:", observer);
    });
  } catch (error) {
    console.error("[main] Neuspješna inicijalizacija mape:", error);
    showBanner(
      "Greška pri učitavanju mape -- provjeri da li je backend pokrenut " +
        "(uvicorn app.main:app) i da su ARCGIS_CLIENT_ID/SECRET podešeni u backend/.env. " +
        "Detalji u browser konzoli."
    );
  }
}

bootstrap();
