# GIS Landscape Identifier (radni naziv) — MVP

> **Status: Phase 1 (project setup + ArcGIS mapa) — u razvoju.**
> Ovo NIJE finalni README. Puni README (problem/demo/arhitektura/setup/limitations/attribution) se piše u Phase 16, prema `docs/architecture-feasibility-review.md`.

Web aplikacija (mobile-first, browser-based) koja odgovara na pitanje **"Šta gledam?"** — korisnik na planini/vidikovcu usmjeri svoj "viewing sector" (heading + field of view + radius), a deterministički GIS engine (geometrija, OpenStreetMap, Copernicus DEM, line-of-sight) identifikuje koji su planinski vrhovi u tom pravcu vidljivi, a koji su zaklonjeni terenom. OpenAI dodaje kratak prirodan opis rezultata — GIS analiza je uvijek prva, AI je uvijek poslednji, kozmetički sloj.

Portfolio projekat — cilj je da demonstrira GIS/Esri/Python/web/AI vještine kroz mali, završiv i tehnički odbranjiv MVP, ne production-ready proizvod.

## Dokumentacija

- [`docs/architecture-feasibility-review.md`](docs/architecture-feasibility-review.md) — kompletna arhitektura, odluke, obrazloženja pragova, API dizajn, backlog po fazama, rizici, test lokacije, deployment plan.
- [`docs/project-brief.md`](docs/project-brief.md) — originalni brief projekta.

## Struktura

```
backend/    FastAPI — deterministički GIS engine (geometrija, OSM, DEM, visibility, location quality, AI)
frontend/   Vanilla JS + ArcGIS Maps SDK for JavaScript — mapa, kontrole, results panel
docs/       Arhitektura, brief, i ostala dokumentacija koja nastaje kroz faze
```

## Trenutni status (Phase 1)

- [x] Repo struktura (backend/frontend/docs).
- [x] FastAPI skeleton sa `/api/v1/health` endpointom.
- [x] Frontend skeleton — ArcGIS `MapView` sa basemap-om, tri prazna `GraphicsLayer`-a (observer/sector/rezultati) pripremljena za naredne faze.
- [x] **Otkriveno tokom Phase 1:** ArcGIS Online organizacija korisnika ne dozvoljava plain API key credentials (admin policy) — arhitektura prilagođena na OAuth 2.0 App authentication (`GET /api/v1/arcgis-token` na backendu, `client_id`/`client_secret` u `backend/.env`). Vidi `docs/architecture-feasibility-review.md`, sekcija 4.
- [x] ArcGIS OAuth App authentication credentials kreirani u AGOL-u, `ARCGIS_CLIENT_ID`/`ARCGIS_CLIENT_SECRET` upisani u `backend/.env` (lokalno, nikad u git — vidi `.gitignore`).
- [x] GitHub Actions CI (`backend-ci.yml`) postavljen i prošao zeleno — `pytest tests/ -v` na GitHub-hosted runneru sa stvarno instaliranim zavisnostima. Vidi `docs/architecture-feasibility-review.md`, sekcija 19.
- [x] Mapa vizuelno potvrđena, bez console grešaka (ArcGIS `MapView` sa basemap-om se učitava, centrirana na Srbiju). Usput otkriven i ispravljen bug: `$arcgis.import()` u SDK 5.1 vraća module direktno, ne umotane u `.default` — vidi `docs/architecture-feasibility-review.md`, sekcija 19.
- [ ] AGOL credit dashboard provjeren (dashboard ima do 24h kašnjenja — provjerava se naknadno, ne blokira dalji razvoj).

## Trenutni status (Phase 2)

- [x] Klik na mapu postavlja/pomjera observer marker (`observerInteraction.js`), bez gomilanja markera na uzastopne klikove.
- [x] Minimalan debug panel prikazuje lat/lon postavljenog observera.
- [x] Backend `ObserverInput` Pydantic model (lat/lon obavezni, GPS/phone dijagnostika opciona za kasnije faze) sa unit testovima za granice koordinata.
- [x] Svi testovi prolaze lokalno (11/11) i na CI-ju.

## Trenutni status (Phase 3)

- [x] Slajderi za heading (0–360°), FOV (20–90°, default 50°) i radius (5–30 km, default 20 km) u `controlsPanel.js`.
- [x] Backend `geometry.py` — `geodesic_distance_km`, `initial_bearing_deg`, `angular_difference_deg`, `is_within_sector` preko `pyproj`/WGS84 elipsoida (ne haversine/Euclidean).
- [x] Viewing sector se crta kao poluprovidan poligon i uživo ažurira na svaku promjenu observera ili slajdera (`sectorGeometry.js` + `sectorRenderer.js`).
- [x] 13 novih unit testova (`test_geometry.py`), uključujući eksplicitan wrap-around test (heading 359° + feature 1°) i granični slučaj sektora. Svi testovi prolaze (25/25, `pytest tests/ -v`).
- [x] Pronađen i ispravljen bug: sektor se nije crtao jer je `Polygon.rings` (sirovi WGS84 lon/lat) bio deklarisan sa `spatialReference: view.spatialReference` (Web Mercator) umjesto `{ wkid: 4326 }` — detalji u `docs/architecture-feasibility-review.md`, sekcija 21.

## Trenutni status (Phase 4)

- [x] `osm.py` — Overpass QL upit za `natural=peak`, in-memory TTL keš, defanzivan `ele` tag parser.
- [x] Privremen dev endpoint `GET /api/v1/osm/peaks` za ručnu verifikaciju (biće obuhvaćen sa `/api/v1/analyze` u Phase 5-9).
- [x] 12 novih unit testova (mock Overpass odgovor, bez zavisnosti od prave mreže u CI-ju). Ukupno 42 backend testa, svi prolaze.
- [x] Pronađen i ispravljen bug: Overpass API zahtijeva `User-Agent` header (bez njega vraća `406 Not Acceptable`) — detalji u `docs/architecture-feasibility-review.md`, sekcija 22.
- [x] Empirijski potvrđena test lokacija (Kopaonik) — stvaran Overpass odgovor sadrži gustu listu imenovanih vrhova (Pančićev vrh, Vučak, Veliki Karaman, ...).

## Trenutni status (Phase 5)

- [x] `select_candidates()` u `geometry.py` — filtrira OSM peakove po radius/FOV sektoru, računa distance/bearing/angular-difference, sortira po relevantnosti.
- [x] Rangiranje: prvo ugaona blizina heading-u, pa distanca kao tiebreaker (elevacija namjerno izostavljena dok DEM nije dostupan — Phase 6).
- [x] `candidate_ranking_max_n = 20` cap za DEM/line-of-sight fazu.
- [x] Dev endpoint `GET /api/v1/osm/candidates` sa `debug` blokom (broj kandidata prije/poslije filtera).
- [x] 7 novih testova (uklj. wrap-around). Ukupno 49 backend testova, svi prolaze.
- [x] Empirijski potvrđeno protiv prave Overpass instance za Kopaonik (uz jedan tranzitorni 504 od Overpass-a, riješen retry-jem — poznat, već dokumentovan rizik).

## Trenutni status (Phase 6)

- [x] `ElevationService.get_elevation(lat, lon)` u `elevation.py` -- Copernicus DEM GLO-30, "download-once, cache-on-disk" pristup (lokalni disk keš po tile-u umjesto GDAL `/vsicurl/` streaming reada -- razlog: nerešiv `UnicodeDecodeError` bag ugrađen u rasterio-jevu kompajliranu ekstenziju, detalji u `docs/architecture-feasibility-review.md`, sekcija 24).
- [x] Usput pronađen i ispravljen nezavisan bug: `PROJ_LIB`/PostGIS konflikt na razvojnoj mašini (rasterio je pokupio pogrešnu `proj.db`).
- [x] Empirijski potvrđena pokrivenost Copernicus GLO-30 Public bucket-a za Kopaonik/Srbiju, i tačnost (DEM 2011.6 m naspram OSM `ele` 2017 m za Pančićev vrh -- razlika u granicama očekivane GLO-30 vertikalne tačnosti).
- [x] Dev endpoint `GET /api/v1/elevation/lookup?lat=&lon=`.
- [x] 13 novih testova (naming konvencija za sve hemisfere, cache-hit/download put, nodata handling -- stvarno `rasterio` čitanje se testira protiv pravog malog GeoTIFF fixture-a, samo mrežni download je mock-ovan). Ukupno 62 backend testa, svi prolaze.

## Trenutni status (Phase 7)

- [x] `LocationQuality` model i `location_quality.py` servis -- `classify_confidence()`, `compute_observer_elevation_m()`, `build_location_quality()` (puna logika i pragovi već odobreni u `docs/architecture-feasibility-review.md`, sekcija 6, prije implementacije).
- [x] Dva granična slučaja dogovorena prije koda: DEM nedostupan -> `confidence: "low"` bez obzira na GPS accuracy; `horizontal_accuracy_m == None` (manual/desktop observer) -> `confidence: "high"` (detalji: sekcija 25).
- [x] Dev endpoint `GET /api/v1/observer/elevation`.
- [x] 15 novih testova (granični slučajevi pragova, oba nova pravila, sastavljanje modela, endpoint). Ukupno 77 backend testova, svi prolaze.
- [x] Ručno potvrđeno za Pančićev vrh -- `observer_elevation_m` = DEM + eye height, `confidence: "high"` i sa i bez GPS accuracy podatka.

## Trenutni status (Phase 8 + automatski Overpass retry)

- [x] `visibility.py` -- `check_visibility()` (geodesic sample tačke duž linije, batch DEM sampling, granični slučaj: jednak ugao = vidljivo ne blokirano, "DEM gap" se ne tretira kao blokada) i `resolve_target_elevation()` (OSM `ele` prioritet, DEM fallback, razlika > 50 m se samo bilježi).
- [x] Dev endpoint `GET /api/v1/analyze/preview` -- pun pipeline (observer + location quality -> OSM kandidati -> DEM -> line-of-sight).
- [x] 96 backend testova prolazi; ručno potvrđeno protiv prave Kopaonik lokacije (plauzibilna podjela visible/blocked, nakon jednog tranzitornog Overpass 503 riješenog ručnim retry-jem).
- [x] Automatski Overpass retry dodat kao reakcija na taj 503 (`overpass_max_retries=2`, `overpass_retry_backoff_s=2.0`) -- kod napisan i testovi prošireni, **korisnička `pytest` potvrda još nije urađena**.

## Trenutni status (Phase 9 -- proširenje scope-a: rijeke/vodene površine/parkovi/nacionalni parkovi)

Nakon Phase 8, eksplicitno je odbačen "samo vrhovi" scope -- korisnik pita i "koja je rijeka/koje je mjesto/koji je park ispred mene". Puno obrazloženje (uklj. dva kruga korisničke korekcije protiv centroid-only pristupa) u `docs/architecture-feasibility-review.md`, sekcija 27.

- [x] Tačkasti feature-i prošireni: `place=city|town|village` i `tourism=viewpoint`, pored `natural=peak` (isti pipeline, novo `category` polje). Preimenovano: `OSMPeak`→`OSMPointFeature`, dev endpointi `/osm/points`, `/osm/point-candidates`.
- [x] NOVI area-feature pipeline (`osm_areas.py`, `area_visibility.py`): rijeke/vodene površine/parkovi/nacionalni parkovi sa STVARNOM geometrijom (way -> LineString/Polygon, relation -> Polygon preko `shapely.ops.polygonize()`), geometrijski intersect sa viewing-sector poligonom (`geometry.build_sector_polygon()`), i "mini-viewshed" sampling (više sample tačaka duž presječenog dijela, svaka provjerena preko postojećeg `check_visibility()`, agregirano u `visible_fraction`).
- [x] Novi dev endpoint `GET /api/v1/osm/areas` (sirova geometrija, GeoJSON-oblik) i novo `"area_features"` polje u `/api/v1/analyze/preview`.
- [x] Novi/prošireni testovi: `test_osm_areas.py`, `test_area_visibility.py`, plus izmjene u `test_geometry.py`/`test_osm.py`/`test_analyze.py`.
- [ ] **VAŽNO -- neprovjerena pretpostavka:** cijeli relation→polygon pipeline pretpostavlja da Overpass `out geom;` uključuje punu geometriju relacijskih članova direktno u odgovoru (dokumentovano, standardno ponašanje, ali NIJE moglo biti empirijski testirano iz razvojnog okruženja -- vidi sekciju 27). Prva stvar za ručnu provjeru preko `/api/v1/osm/areas`.
- [ ] Korisnička `pytest` i ručna Swagger verifikacija još nisu urađene za Phase 9 kod -- commit/push čeka to (vidi sekciju 26-27 arhitekture).

Sljedeća faza (nakon verifikacije Phase 8 retry-ja i Phase 9): **Phase 10+ -- mobile geolocation, phone altitude diagnostics, device orientation/compass** (frontend integracija stvarnih senzora, nakon što je backend pipeline dokazan preko manual/dev endpointa na širem setu geografskih feature-a).

## Licenca podataka

Planinski vrhovi dolaze iz © OpenStreetMap contributors (ODbL) preko Overpass API-ja. Elevacija: Copernicus DEM GLO-30 (Copernicus DEM licenca, besplatna upotreba). Puna attribution sekcija dolazi u Phase 16.
