/**
 * Observer marker -- postavljanje preko browser geolocation-a (Phase 10).
 *
 * NAPOMENA (korisnička odluka, 28.09.2026 -- vidi
 * docs/architecture-feasibility-review.md sekcija 38): ovaj modul je do
 * ove izmjene izlagao i `setupObserverInteraction()` -- klik-na-mapu
 * handler iz originalnog brief Phase 2 ("Desktop development mode",
 * tačka 38), koji je bio i obavezan fallback po tački 42 kad geolocation
 * ne radi. Korisnik je eksplicitno tražio da se observer NIKAD ne može
 * postaviti klikom, samo preko dugmeta "Koristi moju lokaciju" -- funkcija
 * je uklonjena (vidi main.js za kontekst i rizik koji ova odluka nosi).
 * `placeObserverMarker()` ostaje jer je i dalje jedini put kojim se
 * observer marker crta, sad isključivo iz main.js-ovog onLocate handlera.
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
