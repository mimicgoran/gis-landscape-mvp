# Frontend — GIS Landscape Identifier (Phase 1)

Vanilla JavaScript (ES moduli) + ArcGIS Maps SDK for JavaScript 5.1. Bez build koraka — samo statički fajlovi.

## Setup

**Napomena:** Korisnikova ArcGIS Online organizacija ima isključeno izdavanje plain "API key"
credentials (admin security policy — vidi poruku "Looking for API key credentials? Contact your
system's administrator for access" u AGOL-u). Zbog toga frontend **ne** koristi statičan
`ARCGIS_API_KEY`, nego dobija kratkotrajan token sa backenda (OAuth 2.0 "App authentication").
Frontend setup je zato u potpunosti na backend strani — vidi `backend/.env.example` i
`docs/architecture-feasibility-review.md`, sekcija 4, za korak-po-korak kreiranje OAuth app-auth
credentials u ArcGIS Online-u. Ovaj frontend folder nema nikakav `.env`/key da se popuni.

**Backend mora biti pokrenut** (`uvicorn app.main:app --reload`, iz `backend/` foldera) prije nego
što se frontend učita — mapa dohvata ArcGIS token sa `http://localhost:8000/api/v1/arcgis-token`
pri startu.

## Pokretanje lokalno

ES moduli zahtijevaju HTTP (ne `file://`). Iz `frontend/` foldera:

```bash
python3 -m http.server 5500
```

ili, ako imaš Node:

```bash
npx serve -l 5500 .
```

Zatim otvori `http://localhost:5500` (uz pokrenut backend na portu 8000).

## Definition of Done za Phase 1

- [ ] Backend vraća validan token na `GET /api/v1/arcgis-token` (provjeri u browseru ili `curl`).
- [ ] Mapa se učitava bez grešaka u browser konzoli.
- [ ] Basemap je vidljiv (topo-vector ili Web Map iz AGOL-a ako je `ARCGIS_WEB_MAP_ITEM_ID` podešen).
- [ ] Provjeren ArcGIS Online credit dashboard nakon dan-dva korišćenja (potvrda pretpostavke iz review-a, sekcija 4).
