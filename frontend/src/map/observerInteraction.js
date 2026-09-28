/**
 * Observer marker -- postavljanje preko klika na mapu (Phase 2) I preko
 * browser geolocation-a (Phase 10). Oba puta dijele ISTI Point/Graphic/
 * symbol kod (`placeObserverMarker`) da se ne duplira logika na dva mjesta.
 *
 * Manual klik (`setupObserverInteraction`) ostaje aktivan i nakon Phase 10
 * kao OBAVEZAN fallback za slučaj kad geolocation nije dostupan/je odbijen,
 * ili kad developer namjerno želi testirati konkretnu lokaciju (npr.
 * Kopaonik) dok fizički sjedi za računarom (brief, tačka 38: "Desktop
 * development mode").
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
 * Zajednička putanja za manual klik i geolocation -- vidi modul docstring.
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
  // gomilanja markera na svaki klik/geolocation poziv.
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
