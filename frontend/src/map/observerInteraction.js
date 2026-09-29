/**
 * Observer marker -- postavljanje preko browser geolocation-a (Phase 10),
 * i (PRIVREMENO, sekcija 45) preko klika na mapu za demo snimanje.
 *
 * NAPOMENA (korisnička odluka, 28.09.2026 -- vidi
 * docs/architecture-feasibility-review.md sekcija 38): za PRAVE korisnike,
 * observer se postavlja ISKLJUČIVO preko dugmeta "Koristi moju lokaciju" --
 * `setupObserverInteraction()` (klik-na-mapu handler iz originalnog brief
 * Phase 2 "Desktop development mode", tačka 38) je zbog toga bila
 * uklonjena.
 *
 * NAPOMENA (korisnička odluka, 29.09.2026 -- sekcija 45): korisniku treba
 * klik-na-mapu PRIVREMENO, samo dok sa računara snima demo video (mora
 * moći da postavi tačnu, ponovljivu lokaciju prije snimanja ekrana).
 * `setupObserverInteraction()` je zato VRAĆENA (identičan kod kao original,
 * commit 9b20f14 u git istoriji), ali se aktivira SAMO iza
 * `config.ALLOW_MAP_CLICK` zastavice (`?allowMapClick=1` u URL-u) -- za
 * prave korisnike bez tog query parametra, ponašanje je NEPROMIJENJENO
 * (main.js je ne poziva). Vidi main.js i config.js za kompletan mehanizam.
 * `placeObserverMarker()` ostaje zajednička putanja za oba puta (klik i
 * geolocation), kao i originalno prije sekcije 38.
 */

let GraphicClass;
let PointClass;
let createObserverSymbolFn;

async function ensureClassesLoaded() {
  if (!GraphicClass || !PointClass || !createObserverSymbolFn) {
    const [Graphic, Point, symbols] = await Promise.all([
      $arcgis.import("@arcgis/core/Graphic.js"),
      $arcgis.import("@arcgis/core/geometry/Point.js"),
      import("./symbols.js"),
    ]);
    GraphicClass = Graphic;
    PointClass = Point;
    createObserverSymbolFn = symbols.createObserverSymbol;
  }
}

/**
 * Postavlja (briše prethodni i crta novi) observer marker na dat lat/lon.
 * Vidi modul docstring za istoriju (ranije zajednička putanja i za manual klik).
 *
 * @param {import("@arcgis/core/views/MapView").default} view
 * @param {import("@arcgis/core/layers/GraphicsLayer").default} observerLayer
 * @param {number} latitude
 * @param {number} longitude
 * @returns {Promise<{ latitude: number, longitude: number }>}
 */
export async function placeObserverMarker(view, observerLayer, latitude, longitude) {
  await ensureClassesLoaded();

  const point = new PointClass({
    longitude,
    latitude,
    spatialReference: view.spatialReference,
  });

  // Observer je uvijek tačno jedan graphic -- brišemo prethodni umjesto
  // gomilanja markera na svaki geolocation poziv.
  observerLayer.removeAll();
  observerLayer.add(
    new GraphicClass({
      geometry: point,
      symbol: createObserverSymbolFn(),
    })
  );

  return { latitude: point.latitude, longitude: point.longitude };
}

/**
 * Registruje click handler na MapView koji postavlja/pomjera observer
 * marker preko `placeObserverMarker`, i javlja novu poziciju pozivaocu.
 *
 * PRIVREMENO ponovo aktivna funkcija (sekcija 45) -- pozivalac (main.js)
 * je poziva SAMO kad je `config.ALLOW_MAP_CLICK` tačno (`?allowMapClick=1`
 * u URL-u), inače ostaje nepozvana/dormant. Za prave korisnike (bez tog
 * query parametra) observer se i dalje postavlja ISKLJUČIVO preko
 * geolocation dugmeta, vidi modul docstring.
 *
 * @param {import("@arcgis/core/views/MapView").default} view
 * @param {import("@arcgis/core/layers/GraphicsLayer").default} observerLayer
 * @param {(observer: { latitude: number, longitude: number }) => void} onObserverPlaced
 */
export async function setupObserverInteraction(view, observerLayer, onObserverPlaced) {
  await ensureClassesLoaded();

  view.on("click", async (event) => {
    // Sprječava default ponašanje (npr. eventualni popup na budućim
    // slojevima) -- klik na mapu uvijek postavlja observer, nikad ne
    // identifikuje postojeće feature-e (za to služe popup-i na resultsLayer-u,
    // vidi resultsRenderer.js).
    event.stopPropagation();

    const observer = await placeObserverMarker(view, observerLayer, event.mapPoint.latitude, event.mapPoint.longitude);
    onObserverPlaced(observer);
  });
}
