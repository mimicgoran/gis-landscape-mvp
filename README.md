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

Sljedeća faza: **Phase 4 — OSM `natural=peak` integracija** (Overpass API upit, cache, endpoint koji vraća sirove peakove u radijusu).

## Licenca podataka

Planinski vrhovi dolaze iz © OpenStreetMap contributors (ODbL) preko Overpass API-ja. Elevacija: Copernicus DEM GLO-30 (Copernicus DEM licenca, besplatna upotreba). Puna attribution sekcija dolazi u Phase 16.
