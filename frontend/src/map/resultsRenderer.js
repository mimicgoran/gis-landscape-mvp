/**
 * Crta visible/blocked TAČKASTE feature-e (vrhovi/naselja/vidikovci) na
 * resultsLayer, obojene po vidljivosti -- originalni brief Phase 9
 * ("Visible/blocked UI"), uradeno tek sada zajedno sa Phase 10 (vidi
 * glavnu arhitekturu, napomena o procjepu u numeraciji faza).
 *
 * NAMJERNO ograničenje: AREA feature-i (rijeke/vodene površine/parkovi/
 * nacionalni parkovi) se NE crtaju ovdje kao geometrija -- `AnalyzedAreaFeature`
 * (backend model, vidi app/models/feature.py) namjerno ne nosi koordinate/
 * geometriju, samo distancu/bearing prema najbližoj tački, da se ne bi
 * duplirala puna Overpass geometrija u dva različita API odgovora. Area
 * feature-i se zato prikazuju SAMO tekstualno u resultsPanel.js. Crtanje
 * njihove stvarne geometrije na mapi je Future stavka (zahtijeva ili
 * dodavanje geometry polja u AnalyzedAreaFeature, ili dodatan poziv na
 * GET /api/v1/osm/areas sa strane frontenda) -- namjerno odloženo da ova
 * faza ostane frontend-fokusirana bez dodatnih backend izmjena.
 */

let GraphicClass;
let PointClass;
let symbolsModule;

async function ensureClassesLoaded() {
  if (!GraphicClass || !PointClass || !symbolsModule) {
    const [Graphic, Point, symbols] = await Promise.all([
      $arcgis.import("@arcgis/core/Graphic.js"),
      $arcgis.import("@arcgis/core/geometry/Point.js"),
      import("./symbols.js"),
    ]);
    GraphicClass = Graphic;
    PointClass = Point;
    symbolsModule = symbols;
  }
}

/**
 * @param {import("@arcgis/core/layers/GraphicsLayer").default} resultsLayer
 * @param {{ visible_features: object[], blocked_features: object[] }} analysis
 */
export async function renderResults(resultsLayer, analysis) {
  await ensureClassesLoaded();

  resultsLayer.removeAll();

  const graphics = [];

  // Blocked se dodaju PRVO, visible POSLIJE -- kad se markeri preklapaju na
  // mapi, posljednje dodati graphic crta se na vrhu, pa visible feature-i
  // ostaju vizuelno "iznad" blocked-ih (isti princip kao brief tačka 35).
  for (const feature of analysis.blocked_features) {
    graphics.push(createFeatureGraphic(feature, symbolsModule.createBlockedFeatureSymbol(), false));
  }
  for (const feature of analysis.visible_features) {
    graphics.push(createFeatureGraphic(feature, symbolsModule.createVisibleFeatureSymbol(), true));
  }

  resultsLayer.addMany(graphics);
}

function createFeatureGraphic(feature, symbol, isVisible) {
  return new GraphicClass({
    geometry: new PointClass({
      longitude: feature.longitude,
      latitude: feature.latitude,
      spatialReference: { wkid: 4326 },
    }),
    symbol,
    attributes: { osmId: feature.osm_id },
    popupTemplate: {
      title: feature.name ?? "(bez imena)",
      content:
        `${feature.distance_km.toFixed(1)} km, ${Math.round(feature.bearing_deg)}°, ` +
        `${Math.round(feature.elevation_m)} m -- ${isVisible ? "VIDLJIVO" : "ZAKLONJENO"}`,
    },
  });
}
