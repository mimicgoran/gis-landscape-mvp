/**
 * Inicijalizacija ArcGIS mape — Phase 1 scope.
 *
 * Namjerno imperativno (Map/MapView/GraphicsLayer konstruisani u kodu, ne
 * kroz <arcgis-map> web component sa gotovim widgetima) jer projekat treba
 * da demonstrira custom GIS logiku, ne samo sastavljanje gotovih komponenti
 * (vidi docs/architecture-feasibility-review.md, sekcija 4).
 *
 * Autentifikacija: korisnikova ArcGIS Online organizacija ne dozvoljava
 * plain API key credentials, pa se access token dohvata sa backenda
 * (OAuth 2.0 App authentication razmjena, vidi arcgisAuthService.js) prije
 * nego što se bilo šta drugo iz SDK-a učita.
 *
 * Kasnije faze dodaju u iste GraphicsLayer-e (ili nove, posebne layere):
 *   - Phase 2: observer marker (klik na mapu)
 *   - Phase 3: viewing sector poligon
 *   - Phase 9: visible/blocked simboli za vrhove
 */

import { ARCGIS_WEB_MAP_ITEM_ID, DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM } from "../config.js";
import { fetchArcGISAccessToken } from "../services/arcgisAuthService.js";

/**
 * Kreira MapView unutar zadatog kontejnera i vraća reference potrebne
 * ostatku aplikacije.
 *
 * @param {string} containerId - id HTML elementa u koji se mapa montira
 * @returns {Promise<{ view: import("@arcgis/core/views/MapView").default, observerLayer: import("@arcgis/core/layers/GraphicsLayer").default, sectorLayer: import("@arcgis/core/layers/GraphicsLayer").default, resultsLayer: import("@arcgis/core/layers/GraphicsLayer").default }>}
 */
export async function createMapView(containerId) {
  const [esriConfig, Map, WebMap, MapView, GraphicsLayer, accessToken] = await Promise.all([
    $arcgis.import("@arcgis/core/config.js"),
    $arcgis.import("@arcgis/core/Map.js"),
    $arcgis.import("@arcgis/core/WebMap.js"),
    $arcgis.import("@arcgis/core/views/MapView.js"),
    $arcgis.import("@arcgis/core/layers/GraphicsLayer.js"),
    fetchArcGISAccessToken(),
  ]);

  // Access token iz OAuth app-auth razmjene koristi se identično kao
  // statičan API key — SDK ne pravi razliku (vidi Esri dokumentaciju o
  // esriConfig.apiKey). Jedina razlika je da ovaj token ima ograničen
  // vijek trajanja i biće osvježen na sljedećem page loadu (backend cache
  // se brine da ne tražimo novi token od Esri-ja na svaki zahtjev).
  esriConfig.default.apiKey = accessToken;

  // Tri odvojena GraphicsLayer-a umjesto jednog: observer/sector/rezultati
  // se često mijenjaju nezavisno jedni od drugih (npr. rezultati se brišu i
  // ponovo crtaju na svaki API poziv, dok observer marker ostaje) — lakše
  // je čistiti/ažurirati po sloju nego filtrirati graphics unutar jednog.
  const observerLayer = new GraphicsLayer.default({ id: "observer-layer" });
  const sectorLayer = new GraphicsLayer.default({ id: "sector-layer" });
  const resultsLayer = new GraphicsLayer.default({ id: "results-layer" });

  // Ako je u AGOL-u napravljen poseban Web Map item (preporučeno u review-u,
  // sekcija 4), koristimo njega radi basemap-a; inače fallback na map
  // konstruisan direktno u kodu (i dalje validno za Phase 1 sanity-check).
  const map = ARCGIS_WEB_MAP_ITEM_ID
    ? new WebMap.default({ portalItem: { id: ARCGIS_WEB_MAP_ITEM_ID } })
    : new Map.default({ basemap: "topo-vector" });

  map.addMany([observerLayer, sectorLayer, resultsLayer]);

  const view = new MapView.default({
    container: containerId,
    map,
    center: DEFAULT_MAP_CENTER,
    zoom: DEFAULT_MAP_ZOOM,
    constraints: {
      // Sprječava zumiranje na nivo gdje basemap tiles gube smisao —
      // nema funkcionalni uticaj na GIS logiku, čisto UX detalj.
      minZoom: 4,
    },
  });

  await view.when();

  return { view, observerLayer, sectorLayer, resultsLayer };
}
