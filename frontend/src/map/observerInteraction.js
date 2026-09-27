/**
 * Manual observer — Phase 2.
 *
 * Klik na mapu postavlja (ili pomjera) observer marker. Ovo je namjerno
 * jedini način da se observer postavi u ovoj fazi (aplikacija se prvenstveno
 * razvija na desktopu, bez GPS-a — vidi
 * docs/architecture-feasibility-review.md, sekcija 13, MVP backlog #2, i
 * originalni brief, tačka 38 "Desktop development mode").
 *
 * Od Phase 10 nadalje, ovo ostaje aktivno kao OBAVEZAN fallback za slučaj
 * kad geolocation nije dostupan/je odbijen, ili kad developer namjerno želi
 * testirati konkretnu lokaciju (npr. Kopaonik) dok fizički sjedi za
 * računarom.
 */

/**
 * Registruje click handler na MapView koji postavlja/pomjera observer
 * marker na observerLayer, i javlja novu poziciju pozivaocu.
 *
 * @param {import("@arcgis/core/views/MapView").default} view
 * @param {import("@arcgis/core/layers/GraphicsLayer").default} observerLayer
 * @param {(observer: { latitude: number, longitude: number }) => void} onObserverPlaced
 */
export async function setupObserverInteraction(view, observerLayer, onObserverPlaced) {
  const [Graphic, Point, { createObserverSymbol }] = await Promise.all([
    $arcgis.import("@arcgis/core/Graphic.js"),
    $arcgis.import("@arcgis/core/geometry/Point.js"),
    import("./symbols.js"),
  ]);

  view.on("click", (event) => {
    // Sprječava default ponašanje (npr. eventualni popup na budućim
    // slojevima) — mi ovdje isključivo postavljamo observer, ne
    // identifikujemo postojeće feature-e.
    event.stopPropagation();

    const point = new Point({
      longitude: event.mapPoint.longitude,
      latitude: event.mapPoint.latitude,
      spatialReference: view.spatialReference,
    });

    // Observer je uvijek tačno jedan graphic — brišemo prethodni umjesto
    // gomilanja markera na svaki klik.
    observerLayer.removeAll();
    observerLayer.add(
      new Graphic({
        geometry: point,
        symbol: createObserverSymbol(),
      })
    );

    onObserverPlaced({
      latitude: point.latitude,
      longitude: point.longitude,
    });
  });
}
