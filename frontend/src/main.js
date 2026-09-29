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
 *
 * NAPOMENA (korisnička odluka nakon drugog pravog telefon testa): debug/
 * location-quality panel (`ui/debugPanel.js`, brief sekcija 15/57) je na
 * mobilnom ekranu (bottom:16px, isti ugao kao resultsPanel na uskim
 * ekranima -- vidi styles/main.css media query) fizički prekrivao listu
 * pronađenih objekata. Umjesto finog CSS repozicioniranja, panel je u
 * potpunosti uklonjen iz glavnog UI-ja (`#debugPanel` ostaje u DOM-u sa
 * `hidden`, `debugPanel.js` modul i backend `location_quality`/`debug`
 * polja ostaju netaknuti) -- tačno onako kako brief sekcija 15 eksplicitno
 * dozvoljava: "Ako komplikuje MVP, ovaj panel može biti Phase 2".
 *
 * NAPOMENA (korisnička odluka, 28.09.2026 -- vidi
 * docs/architecture-feasibility-review.md sekcija 38): observer se SADA
 * postavlja ISKLJUČIVO preko dugmeta "Koristi moju lokaciju" (geolocation).
 * Manual klik na mapu za postavljanje observera (originalni brief Phase 2,
 * tačka 38 "Desktop development mode") je namjerno UKLONJEN -- korisnik je
 * eksplicitno prihvatio da ovo krši brief tačku 42 ("Manual mode mora
 * omogućiti testiranje čak i kada geolocation ne radi") u zamjenu za
 * sigurnost da se observer nikad ne pomjeri slučajnim klikom na mapu.
 * Ako geolocation nije dostupan/bude odbijen, aplikacija trenutno nema
 * fallback -- vidi services/geolocationService.js za detalje i najjednostavniji
 * put nazad ako se ovo pokaže kao problem u praksi.
 *
 * NAPOMENA (korisnička odluka, 29.09.2026 -- sekcija 45, PRIVREMENO): za
 * potrebe snimanja demo videa sa računara, klik-na-mapu je ponovo
 * dostupan, ali ISKLJUČIVO iza `config.ALLOW_MAP_CLICK` zastavice
 * (`?allowMapClick=1` u URL-u) -- vidi config.js i
 * map/observerInteraction.js za mehanizam. Bez tog query parametra
 * (podrazumevano, za sve prave korisnike), ponašanje je identično kao
 * gore opisano -- ISKLJUČIVO geolocation dugme.
 *
 * PHASE 12 (kompas): dugme "Koristi kompas" je dio `controlsPanel.js`
 * (ne actionButtons.js) jer mijenja KONTINUIRANU kontrolu (heading slajder),
 * ne pokreće jednokratnu akciju -- vidi `services/deviceOrientationService.js`
 * za browser-kompatibilnost/permisije i `ui/controlsPanel.js` za UI logiku.
 */

import { createMapView } from "./map/mapSetup.js";
import { placeObserverMarker, setupObserverInteraction } from "./map/observerInteraction.js";
import { renderSector } from "./map/sectorRenderer.js";
import { renderResults } from "./map/resultsRenderer.js";
import { initControlsPanel } from "./ui/controlsPanel.js";
import { initResultsPanel } from "./ui/resultsPanel.js";
import { initActionButtons } from "./ui/actionButtons.js";
import { ALLOW_MAP_CLICK } from "./config.js";
import { getCurrentPosition } from "./services/geolocationService.js";
import { fetchAnalysis } from "./services/analyzeService.js";

async function bootstrap() {
  const statusBanner = document.getElementById("statusBanner");
  const statusBannerText = document.createElement("span");
  const statusBannerClose = document.createElement("button");
  statusBannerClose.type = "button";
  statusBannerClose.className = "status-banner-close";
  statusBannerClose.setAttribute("aria-label", "Zatvori upozorenje");
  statusBannerClose.textContent = "✕";
  statusBannerClose.addEventListener("click", () => hideBanner());
  statusBanner.replaceChildren(statusBannerText, statusBannerClose);

  // NAPOMENA (real-device bug, Phase 10 prvi telefon test): ranije se
  // isti dugačak error tekst (npr. sirov Overpass 504 odgovor) upisivao i
  // ovdje I u resultsPanel -- statusBanner nije imao ni max-height ni
  // dugme za zatvaranje, pa se razvukao preko dugmadi u #actionBar i
  // fizički blokirao klik (isti z-index, statusBanner je kasnije u DOM-u).
  // Dugme za zatvaranje + max-height/overflow (vidi styles/main.css) su
  // trajna zaštita bez obzira na dužinu buduće poruke; pozivaoci analyze
  // greške sad prikazuju SAMO kroz resultsPanel (koji već ima scroll),
  // ne i ovdje -- vidi onAnalyze niže.
  function showBanner(message) {
    statusBanner.hidden = false;
    statusBannerText.textContent = message;
  }
  function hideBanner() {
    statusBanner.hidden = true;
  }

  try {
    const { view, observerLayer, sectorLayer, resultsLayer } = await createMapView("viewDiv");
    console.info("[main] MapView spreman.", view);

    const resultsPanel = initResultsPanel();

    // Observer se drži ovdje (ne u kontrolama) jer ga postavlja ISKLJUČIVO
    // geolocation (dugme "Koristi moju lokaciju", vidi onLocate niže) -- ne
    // slajder, ne klik na mapu (uklonjen, vidi napomenu na vrhu fajla).
    // Sector renderer i analyze poziv trebaju i observer i sector parametre
    // na svaku promjenu bilo kog od njih.
    let currentObserver = null;

    function clearStaleResults() {
      // Rezultati važe za observer poziciju u trenutku poziva -- kad se
      // observer pomjeri (nova geolocation), stari rezultati
      // više ne odgovaraju novoj poziciji, pa se sklanjaju umjesto da
      // zavaravajuće ostanu na mapi/panelu dok se "Šta gledam?" ponovo ne
      // pritisne.
      resultsLayer.removeAll();
      resultsPanel.hide();
    }

    const controls = initControlsPanel({
      onChange: (sector) => {
        renderSector(sectorLayer, view, currentObserver, sector);
      },
      // Phase 12: kompas greške (nepodržan browser, odbijena iOS permisija,
      // senzor se ne javlja) prikazujemo istim statusBanner-om kao i
      // geolocation greške (vidi onLocate niže) -- dosljedan obrazac za sve
      // senzorske greške u aplikaciji.
      onCompassError: (message) => {
        showBanner(message);
      },
    });

    const actions = initActionButtons({
      onLocate: async () => {
        hideBanner();
        actions.setLocateLoading(true);
        try {
          const position = await getCurrentPosition();
          await placeObserverMarker(view, observerLayer, position.latitude, position.longitude);
          currentObserver = position;
          renderSector(sectorLayer, view, currentObserver, controls.getSector());
          clearStaleResults();
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
          showBanner("Prvo postavi observera -- koristi dugme 'Koristi moju lokaciju'.");
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

          resultsPanel.render(analysis);
          await renderResults(resultsLayer, analysis);
          console.info("[main] Analiza završena:", analysis.debug);
        } catch (error) {
          console.error("[main] Analiza nije uspjela:", error);
          // Namjerno SAMO resultsPanel ovdje (ne i showBanner) -- vidi
          // napomenu uz showBanner definiciju gore. resultsPanel već ima
          // ograničenu visinu + scroll, pa dugačka greška (npr. sirov
          // Overpass error tekst) ne može prekriti #actionBar dugmad.
          resultsPanel.showError(error.message);
        } finally {
          actions.setAnalyzeLoading(false);
        }
      },
    });

    if (ALLOW_MAP_CLICK) {
      // PRIVREMENO (sekcija 45, ?allowMapClick=1) -- vidi napomenu na vrhu
      // fajla i config.js. Za prave korisnike (bez tog query parametra)
      // ovaj blok se nikad ne izvršava -- ponašanje ostaje nepromijenjeno.
      console.warn(
        "[main] ?allowMapClick=1 aktivan -- klik na mapu postavlja observera (SAMO za demo/dev, vidi config.js)."
      );
      await setupObserverInteraction(view, observerLayer, (observer) => {
        currentObserver = observer;
        renderSector(sectorLayer, view, currentObserver, controls.getSector());
        clearStaleResults();
        console.info("[main] Observer postavljen klikom (?allowMapClick=1):", observer);
      });
    }
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
