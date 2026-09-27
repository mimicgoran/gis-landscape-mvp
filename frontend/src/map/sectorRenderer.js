/**
 * Crta viewing sector poligon na sectorLayer — Phase 3.
 *
 * Geometrijski proračun (koje tačke čine luk sektora) je odvojen u
 * sectorGeometry.js i ne zavisi od ArcGIS SDK-a (čist JS). Ovaj modul samo
 * pretvara te tačke u ArcGIS `Polygon`/`Graphic` objekte i crta ih.
 */

import { buildSectorPolygonRing } from "./sectorGeometry.js";

let PolygonClass;
let GraphicClass;

async function ensureArcgisClassesLoaded() {
  if (!PolygonClass || !GraphicClass) {
    [PolygonClass, GraphicClass] = await Promise.all([
      $arcgis.import("@arcgis/core/geometry/Polygon.js"),
      $arcgis.import("@arcgis/core/Graphic.js"),
    ]);
  }
}

function createSectorSymbol() {
  return {
    type: "simple-fill",
    color: [0, 120, 255, 0.15],
    outline: {
      color: [0, 120, 255, 0.6],
      width: 1.5,
    },
  };
}

/**
 * Ponovo crta viewing sector na sectorLayer za dati observer i sector
 * parametre. Korisnik mora vizuelno razumjeti šta aplikacija smatra
 * njegovim vidnim poljem (brief, tačka 18) — zato se sektor ažurira uživo
 * na svaku promjenu slajdera ili observer pozicije, ne tek na klik dugmeta.
 *
 * Ako observer nije postavljen, sektor se samo briše (nema centra od kog bi
 * se crtao).
 *
 * @param {import("@arcgis/core/layers/GraphicsLayer").default} sectorLayer
 * @param {import("@arcgis/core/views/MapView").default} view
 * @param {{ latitude: number, longitude: number } | null} observer
 * @param {{ headingDeg: number, fovDeg: number, radiusKm: number }} sector
 */
export async function renderSector(sectorLayer, view, observer, sector) {
  sectorLayer.removeAll();

  if (!observer) {
    return;
  }

  await ensureArcgisClassesLoaded();

  const ring = buildSectorPolygonRing(observer, sector.headingDeg, sector.fovDeg, sector.radiusKm);

  // `ring` sadrži sirove WGS84 (lon, lat) parove iz sectorGeometry.js.
  // Polygon.rings se, za razliku od Point-ovih longitude/latitude
  // convenience polja, uzima doslovno kao x/y u navedenom
  // spatialReference-u -- zato OVDJE mora stajati geografski WGS84 (4326),
  // NE view.spatialReference (Web Mercator). ArcGIS SDK automatski
  // reprojektuje graphics između 4326 i Web Mercator-a, pa view i dalje
  // ispravno prikazuje sektor bez ijednog dodatnog import-a.
  const polygon = new PolygonClass({
    rings: [ring],
    spatialReference: { wkid: 4326 },
  });

  sectorLayer.add(
    new GraphicClass({
      geometry: polygon,
      symbol: createSectorSymbol(),
    })
  );
}
