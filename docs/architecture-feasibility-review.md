# GIS Landscape Identification MVP — Architecture & Feasibility Review

**Status:** ODOBRENO od strane vlasnika projekta (septembar 2026). Osnova za PHASE 1 i sve dalje faze. Čuva se u projektu i ažuriraćemo ga ako se arhitektura promijeni tokom razvoja.

---

## 0. Odluke usvojene nakon review-a

Dvije tačke iz prvobitnog nacrta su eksplicitno odlučene:

1. **Earth curvature — OSTAJE VAN MVP-a (Future/Phase 2), ne ulazi u Phase 8.** Moj prvobitni predlog je bio da uđe u MVP jer na 30–50 km pravi grešku od 60–200 m. Vlasnik projekta je odlučio da MVP scope ostaje geografski fokusiran na **Srbiju**, koja nije veliki prostor — praktični radijusi koje ćemo koristiti u test scenarijima (sekcija 15) i podrazumijevani opseg (sekcija 19 originalnog brifa: 5–30 km tipično) su dovoljno mali da je greška od zakrivljenosti Zemlje zanemarljiva (na 20 km ≈ 14 m prije refrakcije, na 30 km ≈ 31 m — mnogo manje nego na 50 km). Formula i dalje ostaje **dizajnirana da se lako doda kasnije** (parametar/config flag u `visibility.py`, isključen po defaultu), tačno kako je i originalni brief tražio ("dizajn treba omogućiti kasnije dodavanje"), ali se ne implementira aktivno u MVP-u. Sekcija 9 je ažurirana u skladu s ovim.

2. **Elevation fusion (phone + DEM) — POTVRĐENO: NE ulazi u MVP, ni kao opcija.** DEM ostaje jedini autoritativni izvor elevacije; phone altitude ostaje čista dijagnostika. Puna geoid-korigovana fuzija ostaje Phase 2 stavka (plan opisan u sekciji 6).

Sve ostalo iz originalnog brifa je tehnički zdravo i implementira se kako je zamišljeno, uz pragove i objašnjenja koja slijede.

---

## 1. Finalna arhitektura

Sistem se sastoji od četiri sloja:

- **Mobile browser sloj** — Geolocation API + Device Orientation API, samo prikupljanje sirovih senzorskih podataka, bez logike.
- **Frontend (ArcGIS Maps SDK for JavaScript, vanilla JS)** — prikaz karte, viewing sector, kontrole, results panel, poziv backend API-ja.
- **Backend (FastAPI)** — deterministički GIS engine: geometrija, OSM, DEM, visibility, location quality. Ovo je "mozak" sistema.
- **Eksterni servisi** — Overpass API (OSM), Copernicus DEM (AWS Open Data), OpenAI API (samo za tekst na kraju), ArcGIS Online (basemap/Web Map).

Ključna odluka koju vrijedi eksplicitno reći: **frontend ne radi nikakvu GIS matematiku osim vizuelnog crtanja sektora.** Sva distance/bearing/visibility logika živi u backendu, testabilna je i nezavisna od browsera. To je direktna posljedica tvog principa "Geospatial analysis first, AI second" — samo prošireno na "i frontend je glup, backend je pametan".

### Frontend: vanilla JS umjesto React — objašnjenje kompromisa

Predlažem **HTML/CSS/vanilla JavaScript (ES moduli)**, ne React + Vite.

Razlog: MVP ima jedan ekran, jednu kartu, jedan rezultat-panel i par kontrola. React donosi build pipeline, state management mentalni overhead i dependency surface koji ovom projektu ne servisira nikakvu stvarnu potrebu — a scope discipline je eksplicitno tvoj prioritet. ArcGIS Maps SDK for JavaScript se prirodno koristi imperativno (kreiraš View, dodaješ Graphics), što se dobro uklapa u vanilla JS bez posebnog "adaptera" kakav bi trebao za React.

Kompromis: portfolio recenzenti (posebno frontend-orijentisani) ponekad očekuju React na CV-u. Ako ti je to bitno za target auditorijum na LinkedInu, React + Vite je i dalje razuman izbor i SDK ima zvaničan React wrapper (`@arcgis/core` + `@arcgis/map-components` ili `arcgis-react`). Ali za MVP koji mora biti završen, vanilla JS je manje pokretnih dijelova. Ako se kasnije pokaže da ti treba React na portfoliju, to je čist rewrite frontend sloja bez diranja backend/GIS logike — što je i dokaz dobre separacije slojeva.

**Preporuka: vanilla JS za MVP.**

---

## 2. Architecture diagram

```mermaid
flowchart TB
    subgraph PHONE["MOBILE BROWSER"]
        GEO["Geolocation API<br/>lat, lon, accuracy,<br/>altitude, altitudeAccuracy"]
        ORI["Device Orientation API<br/>heading (auto) / manual slider"]
    end

    subgraph FE["FRONTEND — ArcGIS Maps SDK for JavaScript (vanilla JS)"]
        MAP["MapView + GraphicsLayer<br/>user marker, viewing sector,<br/>visible/blocked symbols"]
        CTRL["Controls: heading, FOV, radius"]
        RES["Results panel"]
        DBG["Debug / location-quality panel"]
    end

    subgraph BE["BACKEND — FastAPI"]
        GEOM["geometry service<br/>bearing, distance, sector"]
        LQ["location_quality service"]
        OSMSVC["osm service"]
        ELEV["elevation service (DEM)"]
        VIS["visibility service<br/>(line-of-sight)"]
        AI["ai service (OpenAI)"]
    end

    OVERPASS[("Overpass API<br/>OpenStreetMap<br/>natural=peak")]
    DEM[("Copernicus DEM GLO-30<br/>AWS Open Data, COG/S3")]
    ARCGIS[("ArcGIS Online<br/>basemap / Web Map")]
    OPENAI[("OpenAI API")]

    GEO --> FE
    ORI --> FE
    FE -->|"POST /api/v1/analyze"| BE
    MAP -.->|basemap tiles| ARCGIS

    GEOM --> OSMSVC
    OSMSVC -->|bbox/radius query| OVERPASS
    GEOM --> LQ
    LQ --> ELEV
    ELEV -->|raster sample| DEM
    OSMSVC --> VIS
    ELEV --> VIS
    VIS --> AI
    AI -->|structured JSON only| OPENAI

    BE -->|"structured GIS JSON<br/>+ AI natural-language text"| FE
    FE --> RES
    FE --> DBG
```

---

## 3. Technology stack

| Komponenta | Tehnologija | Zašto | Alternative | Trošak |
|---|---|---|---|---|
| Karta / frontend GIS | ArcGIS Maps SDK for JavaScript | Zahtjev projekta; demonstrira Esri skill; puna kontrola nad geometrijom (custom sector) | Leaflet + OSM tiles (besplatnije, ali gubi Esri deo priče) | Vidi sekciju 4 — basemap tile requests su besplatni do praga |
| Frontend jezik | Vanilla JS (ES moduli), HTML, CSS | Mali scope, bez build overhead-a | React + Vite | 0 |
| Backend framework | FastAPI | Async, automatski OpenAPI/Swagger dokumenti, Pydantic native, brz razvoj | Flask (manje "besplatne" dokumentacije), Django (preglomazno) | 0 |
| Validacija / modeli | Pydantic v2 | Tip-sigurni request/response modeli, auto-validacija | dataclasses + ručna validacija | 0 |
| Geodetski proračuni | `pyproj` + ručne formule (haversine/Vincenty varijante) | Tačan geodesic distance/bearing, industrijski standard | `geopy` (wrapper oko istih formula) | 0 |
| Geometrija (sektor) | `shapely` | Konstrukcija poligona sektora, provjera tačaka unutar poligona | Ručna trig implementacija | 0 |
| Rasterio pristup DEM-u | `rasterio` (+ `rioxarray` opciono) | Čitanje Cloud-Optimized GeoTIFF-a direktno sa S3, windowed read | GDAL direktno (niži nivo, više koda) | 0 |
| Numerika | `numpy` | Vektorizovan line-of-sight profil (brže od Python petlje) | čist Python | 0 |
| HTTP klijent | `httpx` (async) | Async poziv ka Overpass i OpenAI, konzistentno sa FastAPI async modelom | `requests` (sinhrono, blokira event loop) | 0 |
| OSM podaci | Overpass API (`overpass-api.de` ili `overpass.kumi.systems`) | Besplatan pristup OSM podacima po prostornom upitu | Vlastita Overpass instanca (nepotrebno za MVP) | 0, uz fair-use limite (sekcija 7) |
| Elevacija | Copernicus DEM GLO-30 preko AWS Open Data (S3, COG) | Besplatno, bez naloga, globalno pokriće, deklarisan vertikalni datum | ArcGIS Location Platform elevation servis (50.000 tačaka/mjesec besplatno) kao dopuna/fallback | 0 |
| AI opis | OpenAI API (npr. GPT-4o-mini klasa modela za trošak) | Već imaš pristup; kratak tekst na kraju pipeline-a | Bilo koji LLM API | Nisko (par centi po demo sesiji ako se ograniči broj tokena) |
| Version control | GitHub | Zahtjev projekta (portfolio) | — | 0 |
| Frontend hosting | GitHub Pages | Besplatno, HTTPS automatski, prirodno se uklapa u "profesionalan repo" narativ | Vercel / Netlify | 0 (vidi sekciju 17) |
| Backend hosting | Render (Free Web Service) | Besplatno, bez kartice, Git-based deploy | Railway (više nije realno besplatan), Fly.io (bez free tier-a) | 0, uz cold-start caveat (sekcija 17) |

---

## 4. Esri arhitektura — šta tačno koristimo i gdje se troše krediti

Ovo je sekcija u kojoj je najvažnije biti precizan, jer credits koštaju stvaran novac ako se pogriješi.

### Šta koristimo iz ArcGIS Online

- **Web Map** (item u tvom ArcGIS Online nalogu) koji definiše basemap i početni extent. Frontend učitava taj Web Map preko `WebMap` klase iz SDK-a umjesto da ručno sastavlja `Map` sa hardcodovanim slojevima. Ovo je opravdano jer: (a) direktno demonstrira ArcGIS Online kao stvarnu infrastrukturu (item se vidi u tvom AGOL nalogu, ima sharing podešavanja, može se javno podijeliti), (b) omogućava da basemap promijeniš iz AGOL-a bez diranja koda.
- **Basemap** unutar tog Web Map-a (npr. Topographic ili Imagery Hybrid — dobar izbor za planinare jer prikazuje relief).
- **Application item** — sam frontend registrujemo kao ArcGIS Online "Application" item (tip: Web Mapping Application), povezan na Web Map. Ovo je čisto organizaciono (vidljivost u AGOL-u, sharing), ne generiše dodatni trošak.

### Šta koristimo iz ArcGIS Maps SDK for JavaScript

- `MapView` (2D je dovoljan i brži za mobile — 3D `SceneView` nije potreban jer ne radimo 3D terrain vizualizaciju u MVP-u).
- `GraphicsLayer` za: observer marker, viewing sector (poluprovidan poligon), visible/blocked simbole za vrhove.
- `Point`, `Polygon` geometrijske klase — sektor gradimo ručno (vidi sekciju 8) i crtamo kao `Polygon` graphic, **ne** kao gotov widget. Ovo direktno adresira tvoj zahtjev da custom logika bude vidljiva, ne sakrivena iza gotovog widgeta.
- `Popup` za klik na vrh (prikaz distance/bearing/elevation/status).
- `geometryEngine` opciono za pomoćne operacije (npr. provjeru da li tačka upada u poligon sektora na frontendu radi live preview-a dok korisnik pomjera slajdere — ali finalna odluka o kandidatima uvijek dolazi iz backend odgovora).

### Autentifikacija — ažurirano u Phase 1 (OAuth 2.0 App authentication umjesto plain API key-a)

Prilikom implementacije Phase 1 otkriveno je da korisnikova ArcGIS Online organizacija ima **isključeno izdavanje plain "API key" credentials** (admin security policy — AGOL prikazuje "Looking for API key credentials? Contact your system's administrator for access" i nudi samo OAuth 2.0 opcije). Ovo mijenja tehnički detalj (ne suštinu) sekcije 4:

- Umjesto statičnog, u frontend kod upisanog API key-a, koristimo **OAuth 2.0 credentials tipa "App authentication"** (client_credentials grant — pristup bez prijave korisnika, isti use-case kao plain API key).
- **`client_id` i `client_secret` ostaju na backendu** (`backend/.env`, isti nivo tajnosti kao `OPENAI_API_KEY`) — ovo je bitna razlika u odnosu na plain API key, koji je po dizajnu bio klijentski/javan. Backend (`app/services/arcgis_auth.py`) razmjenjuje ih za kratkotrajan access token preko ArcGIS OAuth token endpointa i servira ga frontend-u preko novog `GET /api/v1/arcgis-token` endpointa (token se cache-uje u memoriji procesa dok ne istekne).
- Frontend (`src/services/arcgisAuthService.js`) dohvata taj token pri startu i postavlja ga na `esriConfig.apiKey` — SDK ovo tretira identično kao statičan API key (Esri dokumentacija to potvrđuje: access token iz OAuth app-auth razmjene se koristi "isto kao API key" u zahtjevima).
- Ovo je zapravo **bolja** sigurnosna praksa za portfolio nego plain API key (jasnija demonstracija razumijevanja Esri auth modela), samo zahtijeva jedan dodatni backend endpoint koji plain-key pristup ne bi tražio.
- Ako je korisnik u budućnosti org admin ili dobije pristup od admina, plain API key ostaje jednostavnija alternativa — kod je strukturiran tako da bi zamjena bila lokalizovana samo u `mapSetup.js`/`arcgisAuthService.js`, bez uticaja na ostatak sistema.

### Gdje se troše krediti — i koliko

| Servis | Troši credits? | Približan trošak | Napomena |
|---|---|---|---|
| Prikaz basemap tiles u Web Map-u (JS SDK, standardni Esri basemap stilovi) | Metered kroz ArcGIS Location Platform tile model: **2.000.000 tile requests/mjesec besplatno**, zatim $0.15/1000 tiles | Za demo/portfolio saobraćaj, praktično nedostižno u besplatnoj zoni | Isti model se primjenjuje bez obzira da li se koristi plain API key ili OAuth app-auth access token (vidi podsekciju "Autentifikacija" iznad) — credential tip utiče na to KAKO se autentifikujemo, ne NA ŠTA se troši. Kako se tvoja postojeća ArcGIS Online organizaciona licenca tačno poklapa sa ovim (da li org dobija odvojenu, često veću ili "uključenu" alokaciju za bazne basemape) **nije mi pouzdano potvrđeno iz dokumentacije koju sam pronašao** — preporuka je da se ovo empirijski provjeri u Phase 1 (praviš prazan Web Map + JS SDK app, gledaš credit dashboard u AGOL-u par dana) prije nego što se osloniš na broj. |
| Query Elevation / Profile / Viewshed geoprocessing alati u ArcGIS-u | **Ne** — Esri je ova tri alata učinio besplatnim (više ne troše credits) | 0 | Mi ionako ne koristimo ove alate — radimo vlastiti line-of-sight nad Copernicus DEM-om, ovo je samo za informaciju ako se ikad odluči koristiti Esri-jev elevation servis kao alternativu. |
| ArcGIS Location Platform elevation point servis (`/elevation/at-point`) | Da, ali sa **50.000 elevation points/mjesec besplatno** | 0 unutar besplatne zone | Ne koristimo ga kao primarni izvor (koristimo Copernicus DEM direktno radi rasterio/DEM skilla), ali dokumentujemo kao validacioni alat (sekcija 16) i kao Phase 2 fallback ako Copernicus pipeline ikad zakaže. |
| Geocoding (World Geocoding Service) | Da, 40 credits/1000 geokodiranja | Ne koristimo geocoding u MVP-u (nema pretrage adresa) | 0 |
| Routing | Da | Ne koristimo | 0 |
| Feature/imagery storage | Da, ali samo ako hostujemo feature layer | Ne hostujemo feature layer (peak podaci dolaze live iz Overpass-a, ne skladište se u AGOL-u) | 0 |

### Kako minimizujemo credit usage

1. Ne hostujemo nikakav feature layer u AGOL-u — svi geografski objekti (peaks) dolaze runtime iz Overpass-a i vraćaju se kao JSON, crtaju se kao klijentski `Graphic` objekti. Nema storage troška.
2. Ne koristimo AGOL geocoding ni routing.
3. Koristimo 2D `MapView`, jedan basemap, bez dodatnih premium slojeva (Imagery sa visokom rezolucijom, demografski slojevi itd. bi trošili credits — izbjegavamo ih).
4. DEM podatke povlačimo direktno sa AWS Open Data (Copernicus), ne kroz plaćeni Esri elevation servis, čime elevation dio pipeline-a potpuno izlazi iz AGOL credit ekonomije.
5. Prije javnog objavljivanja demoa, provjerimo AGOL credit dashboard nakon dan-dva testiranja da potvrdimo pretpostavku o basemap tile trošku.

---

## 5. DEM strategija

### Analiza

**Copernicus DEM GLO-30** je ispravan izbor. Ključne činjenice (provjereno kroz AWS Registry of Open Data i Copernicus dokumentaciju):

- **Pristup:** javni S3 bucket `copernicus-dem-30m` (region `eu-central-1`), format **Cloud-Optimized GeoTIFF (COG)**, dostupan bez AWS naloga (`aws s3 cp --no-sign-request` ili direktan HTTPS pristup). Postoji i STAC katalog za pretragu tile-ova po bounding box-u.
- **Licenca:** besplatna za opštu upotrebu ("free and open" prema Copernicus DEM licenci).
- **Rezolucija:** 30 m horizontalna (GLO-30 Public verzija; postoji i GLO-90 sa 90 m, ne koristimo je).
- **Vertikalni datum:** orthometric height iznad **EGM2008 geoid-a** (EPSG:3855). Ovo je ključna činjenica za sekciju 6.
- **Vertikalna tačnost:** DEM sadrži poseban **Height Error Mask (HEM)** band koji procjenjuje standardnu devijaciju po pikselu (raspon otprilike 0.09–43 m, zavisno od terena) — ovo je koristan, dokumentovan signal koji možemo (opciono, Phase 2) izložiti kao dodatnu dijagnostiku, jer je bolji od paušalnog "±X m" broja.
- **Downloadovanje tile-ova nije potrebno unaprijed.** Zahvaljujući COG formatu i `rasterio`-vom windowed read-u, možemo čitati samo potreban prozor piksela direktno preko HTTP range requestova, bez preuzimanja cijelog tile-a (~25 MB po 1°×1° tile-u na 30 m). Za MVP sa radijusom do 50 km, potrebno je 1–4 susjedna tile-a po zahtjevu.
- **Performanse:** prvi pristup tile-u ima latenciju (S3 GET + network), ali može se cache-ovati na disku backend servera (jednostavan lokalni fajl-cache po imenu tile-a) da se izbjegne ponovno preuzimanje pri sljedećim zahtjevima u istoj oblasti — korisno za demo i testiranje gdje se ista test-lokacija poziva više puta.
- **ArcGIS opcije:** postoji alternativa (ArcGIS Location Platform elevation servis, 50.000 tačaka/mjesec besplatno) — vidi sekciju 4. Ne biramo je kao primarnu jer direktan rad sa DEM rasterom (rasterio, windowed read, sampling) je upravo ono što brief traži da se demonstrira kao GIS/Python vještina; gotov REST elevation servis bi tu vještinu sakrio iza jednog API poziva.

### Preporuka

Direktan pristup S3 COG-u preko `rasterio` + lokalni disk cache tile-ova. Bez ArcGIS kredita, bez preuzimanja cijelog globalnog dataseta, bez servera koje treba održavati.

### Napomena o "30 m DEM" (tvoja tačka 26)

Bitno razlikovati:
- **Horizontalna prostorna rezolucija (30 m)** — veličina piksela, tj. koliko je terena "usrednjeno" u jednu vrijednost. Ne govori ništa o tome koliko je ta vrijednost tačna.
- **Vertikalna tačnost** — koliko se DEM vrijednost razlikuje od stvarne visine terena na tom mjestu. Za Copernicus DEM GLO-30 ovo je tipično reda veličine 1–4 m u umjereno strmom terenu (variira, i HEM band to kvantifikuje po pikselu), što je mnogo bolje od "±30 m" pogrešne pretpostavke.
- Dodatni efekat: **horizontalna GPS greška korisnika** (npr. ±15 m) znači da tačka koju šaljemo u DEM možda nije tačno tačka na kojoj korisnik fizički stoji — na strmom terenu to može značiti da smo očitali elevaciju susjednog piksela koji je nekoliko metara viši/niži. Ovo dokumentujemo eksplicitno kao limitation u README-u, ne kao DEM manu nego kao interakciju dva izvora greške.

---

## 6. Phone + DEM elevation strategija (uključujući vertical datum)

Ovo je najosjetljiviji dio sistema jer tiha greška ovdje ne baca exception — samo vrati pogrešan broj. Idem redom kroz tvoja pitanja.

### Šta browser/telefon zapravo vraća

- **`coords.altitude`** — prema W3C Geolocation API specifikaciji, ovo bi trebalo biti visina iznad WGS84 elipsoida. U praksi, ponašanje **zavisi od platforme i nije univerzalno garantovano**: Android-ova `Location.getAltitude()` dokumentacija istorijski govori o WGS84 elipsoidu, dok iOS/Core Location (`CLLocation.altitude`) svoju vrijednost opisuje kao visinu iznad srednjeg nivoa mora (MSL), što je konceptualno bliže orthometric height-u (sličnom onome što DEM koristi), ali ne nužno referisano na isti geoid model (EGM2008) niti sa poznatom tačnošću. Dakle: **ne možemo pouzdano pretpostaviti da su Android i iOS vrijednosti međusobno uporedive, niti da su direktno uporedive sa Copernicus DEM-om**, bez dodatne provjere po uređaju.
- **`coords.altitudeAccuracy`** — kada postoji, procjena je greške u metrima (68% confidence interval prema spec-u), ali mnogi uređaji je uopšte ne vraćaju (`null`), ili vraćaju konzervativno veliku vrijednost.
- **`coords.accuracy`** (horizontalna) — generalno pouzdanija i konzistentnija između platformi nego altitude podaci.

### Vertical datum problem — konkretno

- **DEM (Copernicus GLO-30):** orthometric height iznad EGM2008 geoid-a (EPSG:3855). Ovo je čvrsto dokumentovano i pouzdano.
- **Phone altitude:** nepouzdano definisan referentni sistem, varira po OS-u/proizvođaču/GNSS čipu, i nije eksplicitno deklarisan u samom API odgovoru (nema polja "ovo je EGM96" ili "ovo je WGS84 elipsoid").
- **Razlika između orthometric height i WGS84 ellipsoidal height (geoid undulation) globalno varira otprilike -100 m do +85 m**, i u većini naseljenih regiona je reda veličine nekoliko desetina metara. Ovo NIJE zanemarljivo — ako bismo naivno sabrali/uprosječili phone altitude i DEM elevation bez korekcije, greška bi mogla biti veća od same korisne informacije.
- **Najjednostavniji pouzdan način transformacije, ako bi se radila:** `pyproj` transformacija iz compound CRS `EPSG:4979` (3D geografske koordinate na WGS84 elipsoidu) u `EPSG:3855` (EGM2008 orthometric height), što zahtijeva da PROJ ima instaliran EGM2008 geoid grid fajl (preuzima se jednom, npr. preko `projsync`). Ovo je tehnički najčistije rješenje.
- **Zašto ga ipak ne uvodim u MVP:** transformacija je validna *samo ako* znamo da je ulazna vrijednost zaista WGS84 ellipsoidal height. Za Android to je vjerovatno tačno (po specifikaciji), za iOS vjerovatno nije (MSL-like vrijednost bi se pogrešno transformisala da smo je tretirali kao elipsoidnu). Bez pristupa fizičkim uređajima oba tipa za empirijsko testiranje, primjena "pouzdane" transformacije na nepouzdano klasifikovan ulaz bi nas mogla dovesti u lažni osjećaj preciznosti — što je gore od transparentnog "koristimo DEM, telefon je dijagnostika".

### Odluka za MVP

- **DEM je jedini autoritativni izvor `terrain_elevation`.**
- **`observer_elevation = terrain_elevation + observer_eye_height`** (default 1.7 m, konfigurabilno u backend `core/config.py`, ne u UI-ju).
- **`phone_altitude_m` i `phone_altitude_accuracy_m` se prikupljaju i prikazuju** u `location_quality` odgovoru kao dijagnostika, ali **ne ulaze u proračun observer_elevation**.
- **`elevation_source` je u MVP-u praktično uvijek `"dem"`.** Vrijednosti `"dem_phone_fusion"` i `"dem_phone_disagreement"` su definisane u modelu (schema je spremna), ali logika koja bi ih aktivno postavljala je **Phase 2 stavka** — implementira se tek kad se doda geoid transformacija opisana gore, uz mogućnost testiranja na stvarnim Android i iOS uređajima da se empirijski potvrdi šta svaka platforma zaista vraća.

Ovim je zadovoljen i tvoj eksplicitni zahtjev iz tačke 12: "Ako reliable vertical datum conversion nepotrebno komplikuje MVP: DEM ostaje authoritative source. Phone altitude ostaje diagnostic/quality signal."

### Predloženi pragovi (sa obrazloženjem — nisu naučno "tačni", nego transparentni i podesivi)

**`horizontal_accuracy_m` → confidence:**

| Nivo | Prag | Obrazloženje |
|---|---|---|
| HIGH | ≤ 15 m | Na 30 m DEM rezoluciji, greška ispod pola piksela znači da smo sa velikom vjerovatnoćom uzorkovali ispravnu ili susjednu (praktično identičnu) ćeliju čak i na umjerenom terenu. Ovo je i tipičan raspon standalone GPS fix-a na otvorenom (bez zgrada/gustih krošnji). |
| MEDIUM | 15–50 m | Može promašiti ispravnu DEM ćeliju za 1–2 piksela; na strmom terenu (>30°) to je razlika reda veličine 10–20 m u elevaciji. I dalje upotrebljivo, ali sa oprezom. |
| LOW | > 50 m | Značajan rizik da je uzorkovana pogrešna DEM ćelija; korisnik treba biti upozoren da rezultati (posebno line-of-sight na strmom terenu) mogu biti nepouzdani. |

**`altitudeAccuracy_m` → da li phone altitude uopšte prikazujemo kao "upotrebljivu" dijagnostiku (ne ulazi u proračun, samo utiče na to da li je vrijedno prikazati broj sa naglaskom ili sa upozorenjem):**

| Status | Prag | Obrazloženje |
|---|---|---|
| Upotrebljivo (diagnostic) | ≤ 20 m | Vertikalna GPS preciznost je gotovo uvijek lošija od horizontalne (lošija satelitska geometrija za vertikalnu dimenziju — tipično 1.5–2× horizontalne greške). 20 m je konzervativan, okrugao prag koji isključuje očigledno loše fiksove a ne odbacuje realan raspon vrijednosti koje uređaji zaista prijavljuju. |
| Loše | > 20 m ili `null` | Prikazujemo vrijednost (transparentnost), ali jasno označeno da se ne smatra pouzdanom čak ni kao dijagnostika. |

Ovi pragovi idu u `core/config.py` kao imenovane konstante sa komentarom koji objašnjava logiku (ne magic numbers), i eksplicitno su označeni u README-u kao "inženjerska procjena, ne standard" — tačno kako si tražio/la.

### Location confidence (ukupna ocjena)

Kombinujemo `horizontal_accuracy_m` prag i, sekundarno, da li DEM sampling uopšte uspije (npr. van pokrivenosti = automatski LOW). Phone altitude ne ulazi u confidence ocjenu u MVP-u jer ne ulazi ni u sam proračun — bilo bi nekonzistentno da utiče na confidence a ne i na rezultat.

---

## 7. OSM strategija

- **Overpass query:** za dati observer + radius, gradimo bounding-box ili radius-based Overpass QL upit filtriran na `natural=peak`, npr. `node["natural"="peak"](around:{radius_m},{lat},{lon});` sa `out body;`. Radius filter u samom upitu (Overpass podržava `around`) smanjuje payload prije nego što uopšte stigne do backend filtriranja po sektoru.
- **Filtering:** Overpass vraća sve peakove u krugu (360°), ne samo u FOV sektoru — sektorsko filtriranje (bearing + angular difference) radi backend `geometry` servis nakon što podaci stignu, jer Overpass QL nema nativan "wedge/sector" filter.
- **Atribucija:** OpenStreetMap contributors licenca (ODbL) zahtijeva vidljivu atribuciju. U frontendu: mali "© OpenStreetMap contributors" tekst uz results panel ili u mapinom attribution baru (ArcGIS SDK ima ugrađen attribution widget koji se može proširiti dodatnim tekstom). U README-u: posebna sekcija "Data sources & attribution".
- **Limitations:** OSM pokrivenost `natural=peak` tagova je neujednačena — u nekim planinskim oblastima (npr. dio Dinarida) manje vrhova je označeno nego u dobro mapiranim regijama (Alpe). Ovo direktno utiče na izbor test lokacija (sekcija 15) — biramo oblasti sa gušćim OSM peak pokrivanjem.
- **Caching:** Overpass fair-use politika (javne instance `overpass-api.de`/`overpass.kumi.systems`) preporučuje do otprilike 10.000 zahtjeva/dan i izbjegavanje identičnih ponovljenih upita. Za MVP portfolio saobraćaj ovo nije rizik, ali dodajemo **jednostavan in-memory TTL cache** (npr. keyed by zaokruženi lat/lon + radius bucket, TTL npr. 24h, jer se planinski vrhovi ne pomjeraju) da izbjegnemo nepotreban repeat-query tokom demoa/testiranja i da smo dobri građani prema besplatnom javnom servisu. Vlastita Overpass instanca nije potrebna za ovaj obim.

---

## 8. Viewing sector algoritam

**Ulazi:** `lat`, `lon`, `heading_deg` (0–360, 0 = sjever, u smjeru kazaljke), `fov_deg`, `radius_km`.

### Preporučeni opsezi za FOV i radius (sa obrazloženjem)

**FOV: opseg 20°–90°, default 30°** (promijenjeno sa 50° -- korisnička odluka nakon prvog pravog telefon testa, vidi sekciju 33; opseg i njegovo obrazloženje ostaju nepromijenjeni ispod).
- Ispod 20° sektor postaje toliko uzak da ga i mala greška u headingu (compass jitter, nesigurna ruka, manual slider netačnost od par stepeni) lako "promaši" — korisnik bi morao biti gotovo idealno usmjeren da vidi bilo šta.
- Iznad 90° sektor prestaje da bude "pravac u kojem gledam" i postaje "skoro sve oko mene", što poražava svrhu aplikacije (usmjerena identifikacija, ne opšti pregled).
- 50° kao default je dovoljno široko da apsorbuje tipičan compass šum i nesavršeno držanje telefona, a i dalje dovoljno usko da odgovor osjeti kao "u tom pravcu", ne "na cijelom horizontu".

**Radius: opseg 5–30 km, default 5 km** (promijenjeno sa 20 km -- ista odluka, vidi sekciju 33; options npr. 5 / 10 / 20 / 30 km, opseg i donja granica ostaju kao ispod).
- Gornja granica namjerno spuštena sa 50 km (koliko je originalni brief predlagao kao opciju) na 30 km, direktno kao posljedica odluke iz sekcije 0 da earth curvature ne ulazi u MVP: na 30 km greška zanemarivanja zakrivljenosti je ≈31 m (prije refrakcije), što je i dalje razuman i dokumentovan limitation; na 50 km bi ta greška narasla na ≈196 m, što bi ozbiljno ugrozilo "tehnički odbranjiv" kvalitet line-of-sight odluka blizu horizonta. Ako se scope ikad proširi izvan Srbije sa potrebom za većim radijusima, tada se prvo aktivira curvature korekcija (feature-flag iz sekcije 9), pa tek onda podiže gornja granica radiusa.
- Donja granica od 5 km i default od 20 km su usklađeni sa tipičnim razmacima između planinskih vrhova u Srbiji (sekcija 15) — dovoljno da uhvati koristan broj kandidata bez nepotrebnog opterećenja Overpass upita i line-of-sight prolaza za vrhove koji su praktično van dometa golog oka po prosječnoj vidljivosti.

**Koraci:**

1. **Granice sektora:** `start_bearing = (heading - fov/2) mod 360`, `end_bearing = (heading + fov/2) mod 360`. Modulo aritmetika je obavezna zbog wrap-around slučaja (heading 350°, FOV 40° → sektor 330°–10°, prolazi kroz 0°/360°).
2. **Geodesic distance & initial bearing** (observer → kandidat): koristimo standardnu geodesic formulu (npr. preko `pyproj.Geod.inv()`, koji koristi WGS84 elipsoid, ne sferu — tačnije od haversine na velikim udaljenostima, a implementaciono podjednako jednostavno jer je `pyproj` već dependency).
3. **Angular difference** (bearing kandidata naspram heading-a): `diff = min(abs(bearing - heading), 360 - abs(bearing - heading))` — ovo ispravno hvata wrap-around (npr. heading 359°, feature na 1° → diff = 2°, ne 358°).
4. **Sector inclusion test:** kandidat je unutar sektora ako je `diff <= fov/2` **i** `distance <= radius_km`. (Napomena: `diff <= fov/2` je matematički ekvivalentno testu granica sektora iz koraka 1, ali je implementaciono jednostavnije i manje podložno wrap-around bugovima — pa ga koristimo kao stvarnu provjeru, dok su `start_bearing`/`end_bearing` iz koraka 1 samo za crtanje poligona.)
5. **Polygon construction (za crtanje na mapi):** niz tačaka duž luka od `start_bearing` do `end_bearing` (npr. svakih 2–5°, izračunatih preko "destination point given bearing and distance" formule) plus observer tačka u centru, zatvoreno u poligon. Ovo se računa i na backendu (za konzistentnost ako se ikad vrati u response) i duplira jednostavnom verzijom na frontendu za live preview dok korisnik pomjera slajdere (bez network round-trip-a za svaki pokret slajdera) — izvor istine za stvarne rezultate je uvijek backend.

**Testovi koji moraju postojati (vidi i sekciju 14):** heading 359° + feature na 1° (mora biti unutra ako je FOV dovoljan), FOV koji prelazi 360° granicu, feature tačno na granici sektora (edge case sa `<=` vs `<`).

---

## 9. Line-of-sight algoritam

**Za svaki kandidat (nakon FOV/radius filtriranja):**

1. Generiši geodesic liniju observer → target.
2. **Sample spacing:** ~30 m (jednako DEM rezoluciji). Obrazloženje: sampling finiji od same rezolucije rastera ne dodaje stvarnu informaciju (između dva susjedna piksela DEM samo interpolira), a sampling rjeđi od rezolucije rizikuje da preskoči uzak teren-obstacle (npr. greben) između dvije tačke. Jedan sample po pikselu je razuman balans. Tradeoff je eksplicitan: gušći sampling = tačnije ali sporije (posebno na 30 km sa ~1000 tačaka po kandidatu); rjeđi = brže ali rizik propuštanja prepreke — 30 m je kompromis koji prati rezoluciju izvora podataka, ne proizvoljan broj.
3. Za svaku sample tačku: DEM elevation (rasterio) + distanca od observera.
4. **Elevation angle** za svaku terensku tačku: `angle_i = atan2(terrain_elevation_i - observer_elevation, distance_i)`.
5. **Target angle:** ista formula sa target elevation/distance.
6. **Earth curvature/refrakcija — NIJE uključena u MVP** (vidi sekciju 0: scope je Srbija, radijusi su mali dovoljno da je efekat zanemarljiv — na 20 km ≈ 14 m, na 30 km ≈ 31 m prije refrakcije). Modul je ipak dizajniran da se ovo doda kao izolovana korekcija (`curvature_drop(d) = (1 - k) * d² / (2R)`, standardni `k ≈ 0.13`) bez diranja ostatka algoritma — jedan opcioni term koji se po potrebi doda u koraku 4, iza feature-flag-a u `core/config.py`. Ostaje Future/Phase 2 stavka, aktivira se lako ako se scope ikad proširi van Srbije.
7. **Odluka:** ako bilo koja terenska tačka između observera i targeta ima `angle_i > target_angle`, target je **BLOCKED**. Inače **VISIBLE**.
8. **Target elevation izvor:** OSM `ele` tag ako postoji i numerički je smislen (npr. u razumnom rasponu, ne 0 ili negativan za planinski vrh) — inače DEM na target koordinati. Ako se OSM `ele` i DEM elevation na istoj tački razlikuju za više od nekog praga (npr. 50 m — DEM na vrhu planine ima tendenciju da blago potcijeni pravi vrh zbog 30 m usrednjavanja), **ne biramo automatski "tačan"** — zabilježimo oba broja i `elevation_source`, i razliku kao debug/discrepancy flag. Za MVP: prioritet je OSM `ele` kad postoji (jer je to obično ručno unesena, precizna izmjerena visina vrha), DEM kao fallback.

**Limitations koje idu u README:** ovo nije puni raster viewshed (ne provjerava zaklanjanje van linije observer-target, npr. bočni objekti); tačnost je ograničena DEM rezolucijom i horizontalnom GPS greškom observera; ne uzima u obzir vegetaciju/objekte (DEM, ne DSM) — što znači da šuma ili zgrada mogu u stvarnosti blokirati pogled koji naš model označi kao VISIBLE. Ovo je eksplicitno navedeno kao poznato ograničenje, ne kao skriveni bug.

---

## 10. Data flow — jedan kompletan request

```
TELEFON
  → Geolocation API: {lat, lon, accuracy, altitude?, altitudeAccuracy?}
  → Device Orientation API: heading (ili manual slider ako compass nedostupan/odbijen)
      ↓
FRONTEND (ArcGIS Maps SDK)
  → prikazuje observer marker + live preview sektora (heading/FOV/radius slajderi)
  → korisnik klikne "What am I looking at?"
  → POST /api/v1/analyze { observer: {...}, heading_deg, fov_deg, radius_km }
      ↓
BACKEND — FastAPI
  1. geometry service: validacija inputa (Pydantic)
  2. location_quality service: horizontal_accuracy → confidence; DEM lookup na observer tački
  3. osm service: Overpass query (cache-provjera prvo) → sirovi peak candidates u krugu
  4. geometry service: distance + bearing + angular_diff za svaki peak → filter po FOV/radius → top-N kandidata (ranking, sekcija 13)
  5. elevation service: DEM sampling za observer + svaki kandidat target
  6. visibility service: line-of-sight za svaki kandidat → VISIBLE/BLOCKED + profile
  7. sastavljanje strukturiranog JSON odgovora (observer diagnostics, visible_features, blocked_features)
  8. ai service: šalje SAMO taj strukturirani JSON OpenAI-ju sa strogim system promptom → kratak prirodan opis
      ↓
FRONTEND
  → prikazuje visible/blocked simbole na mapi
  → results panel (lista sa distance/elevation/bearing/status)
  → AI opis kao tekst
  → debug panel (location quality, brojevi kandidata po fazi filtriranja)
      ↓
KORISNIK vidi odgovor na "šta gledam"
```

Ako OpenAI korak (8) ne uspije, koraci 1–7 i dalje vraćaju punu strukturiranu tabelu rezultata frontend-u — AI opis je opcioni dodatak, ne blokirajući korak (tvoj zahtjev iz tačke 33/42).

---

## 11. API design

Namjerno minimalan broj endpointa.

### `POST /api/v1/analyze`

**Request:**
```json
{
  "observer": {
    "latitude": 43.123,
    "longitude": 20.456,
    "horizontal_accuracy_m": 6.4,
    "phone_altitude_m": 1248.0,
    "phone_altitude_accuracy_m": 9.0
  },
  "heading_deg": 247.0,
  "fov_deg": 45.0,
  "radius_km": 20.0
}
```
(`phone_altitude_m` i `phone_altitude_accuracy_m` su opcioni/nullable — sve ostalo je obavezno.)

**Response** (Pydantic model `AnalysisResponse`):
```json
{
  "observer": {
    "latitude": 43.123,
    "longitude": 20.456,
    "dem_elevation_m": 1241.0,
    "observer_eye_height_m": 1.7,
    "observer_elevation_m": 1242.7,
    "heading_deg": 247.0,
    "fov_deg": 45.0,
    "radius_km": 20.0
  },
  "location_quality": {
    "horizontal_accuracy_m": 6.4,
    "phone_altitude_m": 1248.0,
    "phone_altitude_accuracy_m": 9.0,
    "dem_elevation_m": 1241.0,
    "selected_ground_elevation_m": 1241.0,
    "elevation_source": "dem",
    "confidence": "high"
  },
  "visible_features": [
    {
      "osm_id": 123456,
      "name": "Example Peak",
      "latitude": 43.2,
      "longitude": 20.7,
      "distance_km": 12.4,
      "bearing_deg": 251.0,
      "elevation_m": 1832.0,
      "elevation_source": "osm",
      "visibility": "visible"
    }
  ],
  "blocked_features": [
    {
      "osm_id": 456789,
      "name": "Other Peak",
      "distance_km": 19.2,
      "bearing_deg": 241.0,
      "elevation_m": 2050.0,
      "elevation_source": "dem",
      "visibility": "blocked"
    }
  ],
  "ai_description": "Gledaš približno prema jugozapadu. Najistaknutiji identifikovani vrh u tom pravcu je Example Peak, udaljen oko 12 km...",
  "debug": {
    "osm_candidates_total": 34,
    "candidates_after_fov_filter": 9,
    "candidates_analyzed": 9,
    "visible_count": 3,
    "blocked_count": 6
  }
}
```

### `GET /api/v1/health`

Prost health-check (200 OK + verzija) — koristan i za osnovni uptime monitoring i kao "keep-warm" ping protiv Render cold-start-a (sekcija 17).

To je to — dva GIS endpointa. Elevation profile (za budući chart) se po potrebi dodaje kao opciono polje unutar `visible_features`/`blocked_features` (`profile: [...]`), ne kao poseban endpoint, jer se prirodno računa u istom pipeline prolazu.

**Phase 1 dodatak (infrastrukturni, ne GIS endpoint):** `GET /api/v1/arcgis-token` — vraća `{ "access_token": "..." }` za ArcGIS OAuth app-auth (vidi sekciju 4, "Autentifikacija"). Ovo ne broji se protiv "minimalan broj endpointa" principa jer nije dio GIS API-ja — to je infrastrukturni detalj nastao zbog admin ograničenja na korisnikovom AGOL nalogu, analogan npr. health check-u.

---

## 12. Project structure

### Backend

```
backend/
  app/
    main.py                  # FastAPI app, router include, CORS, startup DEM cache warm-up
    api/
      routes/
        analyze.py            # POST /api/v1/analyze
        health.py             # GET /api/v1/health
        arcgis_token.py        # GET /api/v1/arcgis-token (Phase 1 dodatak — vidi sekciju 4, "Autentifikacija")
    models/
      observer.py             # ObserverInput, ObserverDiagnostics
      feature.py               # FeatureResult, Visibility enum
      location_quality.py      # LocationQuality, ElevationSource, Confidence enum
      analysis.py               # AnalysisRequest, AnalysisResponse (kompozicija gornjih)
    services/
      geometry.py              # bearing, geodesic distance, angular diff, sector, ranking
      osm.py                   # Overpass query + cache
      elevation.py             # rasterio DEM sampling + tile cache
      location_quality.py      # thresholds → confidence, elevation_source odluka
      visibility.py            # line-of-sight, curvature/refraction, profile
      arcgis_auth.py           # OAuth app-auth token exchange + in-memory cache (Phase 1 dodatak)
      ai.py                    # OpenAI poziv, system prompt, graceful fallback
    core/
      config.py                # env vars, pragovi (thresholds), eye height, OSM/DEM URLs
    tests/
      test_geometry.py
      test_visibility.py
      test_location_quality.py
      test_osm.py               # sa mock Overpass response
  requirements.txt
  .env.example
  .gitignore
```

Napomena na tvoj predlog: spojio sam `models/` (Pydantic) bez posebnog `schemas/` sloja — za MVP veličine ovog projekta, Pydantic model *je* i domain model i API schema; dodavanje posebnog sloja bi bio unnecessary design pattern koji brief eksplicitno traži da izbjegavamo (tačka 56).

### Frontend

```
frontend/
  index.html
  src/
    main.js                    # bootstrap: MapView init, event wiring
    map/
      mapSetup.js               # WebMap/MapView init, GraphicsLayer setup
      sectorGeometry.js          # frontend preview sektora (bearing/FOV/radius → Polygon)
      symbols.js                 # visible/blocked/observer symbol definicije
    services/
      geolocationService.js      # Geolocation API wrapper + error handling
      orientationService.js      # DeviceOrientationEvent + iOS permission flow + manual fallback
      analyzeApi.js               # fetch POST /api/v1/analyze
    ui/
      controlsPanel.js            # heading/FOV/radius kontrole
      resultsPanel.js              # lista visible/blocked
      debugPanel.js                 # location quality / debug info (expandable)
    utils/
      formatters.js                # formatiranje distance/elevation/bearing za prikaz
  styles/
    main.css
  .env.example                   # (samo ne-tajni frontend config, npr. ArcGIS API key placeholder — NE OpenAI key)
```

---

## 13. MVP backlog

Podijeljeno prema tvom predloženom redoslijedu faza (1–16), sa manjim taskovima unutar svake.

| # | Faza | Cilj | Implementiramo | Kako testiramo | Definition of Done |
|---|---|---|---|---|---|
| 1 | Project setup + ArcGIS map | Radna osnova za sve dalje | Repo struktura, `MapView` sa basemap-om iz Web Map-a, prazan `GraphicsLayer` | Ručno: mapa se učitava u browseru | Mapa vidljiva, bez console grešaka, AGOL credit dashboard provjeren |
| 2 | Manual observer | Postavljanje observera bez GPS-a | Klik na mapu → observer marker + backend `ObserverInput` model (bez API poziva još) | Ručno: klik postavlja marker na tačnu lokaciju | Marker se pomjera na klik, koordinate ispisane u debug panelu |
| 3 | Heading + FOV + sektor | Vizuelni viewing sector | `sectorGeometry.js`, slajderi za heading/FOV/radius, backend `geometry.py` (bearing, sector inclusion) | Unit testovi za bearing/angular diff/wrap-around (359°+1° slučaj) | Sektor se ispravno crta i ažurira uživo; testovi prolaze |
| 4 | OSM `natural=peak` integracija | Dohvatanje stvarnih vrhova | `osm.py` (Overpass query + cache), endpoint koji vraća sirove peakove u radijusu | Integration test protiv prave Overpass instance za poznatu lokaciju | Lista peakova sa imenom/koordinatama/`ele` se vraća i loguje |
| 5 | Distance + bearing + candidate filtering | Filtriranje na kandidate unutar sektora | Kompletiranje `geometry.py` pipeline-a (OSM → distance/bearing → FOV/radius filter → ranking) | Unit testovi sa poznatim koordinatama i ručno izračunatim distance/bearing vrijednostima | Broj kandidata prije/poslije filtera vidljiv u debug panelu |
| 6 | DEM integracija | Čitanje elevacije sa Copernicus DEM-a | `elevation.py` (rasterio S3 COG read, tile cache) | Unit test: poznata koordinata → provjera da vraćena elevacija ima smislen red veličine | DEM lookup radi za observer i za target koordinate |
| 7 | Observer elevation + location quality arhitektura | Diagnostic model | `location_quality.py`, pragovi iz sekcije 6, `LocationQuality` model | Unit testovi za sve confidence pragove (HIGH/MEDIUM/LOW granice) | `location_quality` blok se vraća sa ispravnim poljima za sve kombinacije inputa (uklj. `null` altitude) |
| 8 | Line-of-sight engine | Visible/blocked odluka | `visibility.py` sa sampling-om i profile generisanjem (bez curvature korekcije — vidi sekciju 0/9; ostavljen feature-flag hook za kasnije) | Unit testovi sa sintetičkim (ručno konstruisanim) terenskim profilima gdje je odgovor unaprijed poznat | Poznat "zaklonjen" scenario vraća BLOCKED, poznat "otvoren" scenario vraća VISIBLE |
| 9 | Visible/blocked UI | Prikaz rezultata | `resultsPanel.js`, simboli na mapi (vizuelna razlika visible/blocked) | Ručno: end-to-end klik → prikaz | Rezultati vizuelno jasno razlikuju visible/blocked |
| 10 | Mobile geolocation | Zamjena manual observera pravim GPS-om | `geolocationService.js`, permission handling, error stanja | Ručno na telefonu (i desktop fallback ako permission odbijen) | Observer se postavlja iz stvarne lokacije; manual mode i dalje radi kao fallback |
| 11 | Phone altitude diagnostics | Prikaz phone altitude bez uticaja na proračun | Case A–D logika iz sekcije 6 (bez fusion-a), debug panel prikaz | Unit test za sve 4 case-a (null altitude, null accuracy, loša accuracy, dobra accuracy) | Debug panel prikazuje phone altitude kad postoji, `elevation_source` ostaje `"dem"` |
| 12 | Device orientation / compass | Auto heading | `orientationService.js`, iOS `requestPermission()` flow, Android direktan listener, smoothing (samo ako testiranje pokaže potrebu) | Ručno na Android Chrome i iOS Safari | Auto mode radi na oba, manual mode i dalje dostupan kao obavezan fallback |
| 13 | OpenAI explanation | Prirodni opis | `ai.py`, strogi system prompt, graceful degradation ako API ne radi | Unit test sa mock OpenAI response; ručna provjera kvaliteta teksta | Opis se prikazuje kad OpenAI radi; ostatak aplikacije radi i kad ne radi (simulacija greške) |
| 14 | Testing | Kompletna test pokrivenost GIS logike | Kompletiranje `tests/` (geometry, visibility, location_quality, osm sa mock-om) | `pytest` u CI (GitHub Actions) | Svi testovi prolaze, uključujući wrap-around i edge case-ove |
| 15 | Deployment | Javno dostupan HTTPS URL | GitHub Pages (frontend) + Render (backend), env vars podešeni | Ručno: otvoriti URL na telefonu, kompletan flow | Definition of Done iz tvoje tačke 59 zadovoljen |
| 16 | README + diagram + demo | Portfolio finalizacija | README (sekcije iz tvog brifa), Mermaid diagram, GIF/video | Pregled od strane nekog ko projekat ne poznaje | README samostalno objašnjava projekat bez dodatnog konteksta |

---

## 14. Technical risks

| Rizik | Nivo | Objašnjenje | Mitigacija |
|---|---|---|---|
| Vertical datum nekompatibilnost (phone vs DEM) | **HIGH** | Tiha greška, ne baca exception — pogrešan broj izgleda kao ispravan | Riješeno arhitekturom: DEM je jedini autoritativni izvor u MVP-u (sekcija 6) |
| ArcGIS Online credit potrošnja za basemap u kontekstu tvoje postojeće org licence nije 100% potvrđena iz dokumentacije | **MEDIUM** | Mogli bismo pogrešno pretpostaviti "besplatno" | Empirijska provjera u Phase 1 prije nastavka (provjeriti credit dashboard) |
| Compass/browser kompatibilnost (iOS permission flow, Android varijacije po proizvođaču) | **MEDIUM** | Auto heading može biti nepouzdan ili odbijen | Manual mode je obavezan dio MVP-a od početka, ne naknadni dodatak |
| GPS horizontalna tačnost u planinskom/šumovitom terenu | **MEDIUM** | Loš fix može degradirati DEM sampling i cijeli line-of-sight | Location quality model transparentno komunicira nivo povjerenja korisniku |
| DEM pristup (S3 dostupnost, COG windowed read performanse) | **LOW** | AWS Open Data je stabilan i besplatan, ali je eksterna zavisnost | Lokalni disk cache tile-ova; graceful error ako S3 privremeno nedostupan |
| Overpass reliability (javna instanca, rate limiting) | **LOW–MEDIUM** | Javne instance mogu biti spore ili privremeno vratiti 429/504 | Cache + retry sa exponential backoff; jasna poruka korisniku ako trenutno nedostupno |
| Hosting cold starts (Render free tier spava nakon 15 min neaktivnosti) | **MEDIUM** (posebno za LinkedIn demo!) | Prvi request nakon neaktivnosti može trajati ~1 min | Prije snimanja demoa, "probuditi" backend unaprijed (ping `/health`); eventualno keep-alive ping servis ako se pokaže dosadnim tokom razvoja |
| Line-of-sight tačnost (DEM rezolucija, curvature aproksimacija, nema DSM/vegetacije) | **MEDIUM** | Rezultati su tehnički odbranjivi, ne scientific-grade | Eksplicitno dokumentovano kao limitation; validacija po planu iz sekcije 16 |
| OpenAI API dostupnost/trošak | **LOW** | Nekritičan sloj po dizajnu | Graceful fallback — GIS rezultati se prikazuju i bez AI opisa |

---

## 15. Test lokacije

Pošto tačne OSM peak podatke dobijamo tek live-om u Phase 4, koordinate ispod su orijentacione (centar oblasti) — konkretni testni scenariji (tačan lat/lon, očekivani kandidati) se finalizuju nakon prve Overpass integracije, kada vidimo stvarne tagove u tim oblastima. Ovdje definišem *kriterijume izbora* i *kandidat regione* koji ih zadovoljavaju.

**Kriterijumi:** dobro DEM pokriće (Copernicus GLO-30 ima globalno pokriće pa ovo nije diskriminišuće), više OSM `natural=peak` objekata u razumnom radijusu (5–30 km, u skladu sa scope-om iz sekcije 0/8), jasan teren relief (da line-of-sight ima šta da blokira), kombinacija vrhova koji bi trebalo da budu vidljivi i onih zaklonjenih bližim grebenom. Pošto je MVP scope eksplicitno ograničen na **Srbiju** (sekcija 0), sve test lokacije su unutar Srbije — ovim je i originalni zahtjev "najmanje jedna u Srbiji/Balkanu" prirodno nadmašen.

1. **Kopaonik** — planinski masiv sa gustim klasterom vrhova (uklj. Pančićev vrh, najviši vrh Kopaonika) i razuđenim reljefom; dobra OSM pokrivenost jer je poznato planinarsko/skijaško područje. Primarna lokacija za demo.
2. **Stara planina** — izražen greben sa više istaknutih vrhova duž jasne linije, dobar test za "vrh A vidljiv, vrh B odmah iza njega blokiran" scenario.
3. **Tara (Mokra Gora / kanjon Drine)** — izražen kanjonski reljef sa naglim visinskim razlikama na kratkim distancama, dobar stres-test za sampling interval (korak 2, sekcija 9) jer se teren mijenja brzo unutar par stotina metara.

Nakon Phase 4, za svaku lokaciju zapisujemo konkretan deterministic test scenario (`observer lat/lon, heading, fov, radius → expected candidate OSM ID-jevi`) direktno iz stvarnog Overpass odgovora, ne unaprijed pretpostavljen. Ako scope ikad preraste granice Srbije (npr. dodavanje pograničnih planina ili šireg Balkana), lokacije sa mnogo gušćom OSM pokrivenošću i većim tipičnim radijusima (npr. Alpe) postaju relevantne za re-validaciju — i tada se prvo vraća curvature korekcija (sekcija 9), prije podizanja max radiusa.

---

## 16. Validation plan (line-of-sight)

Cilj nije naučno-precizan viewshed engine, nego tehnički odbranjiv rezultat koji možemo objasniti i demonstrirati da "radi razumno". Predložene metode, po prioritetu implementacije:

1. **Elevation profile inspection (ručna, uvijek dostupna):** za par ručno odabranih parova observer/target sa poznatim terenom (npr. gledanje preko doline ka poznatom vrhu), generišemo profile i vizuelno provjeravamo da li linija "ima smisla" — da li teren zaista raste/pada tamo gdje profil kaže.
2. **Sintetički test slučajevi (unit testovi):** ručno konstruisan teren (npr. flat plato + jedan vještački "zid" tačno na pola puta) sa unaprijed poznatim odgovorom (BLOCKED) — najjeftiniji i najpouzdaniji test jer ne zavisi od stvarnih podataka.
3. **Poznati terenski primjeri (sanity check):** parovi lokacija za koje je javno poznato da se međusobno vide (popularni planinarski vidici sa opisanim pogledom na imenovane vrhove) — koristimo kao "da li engine potvrđuje ono što ljudi stvarno prijavljuju".
4. **Poređenje sa ArcGIS elevation/Viewshed servisom** (besplatan, vidi sekciju 4) za nekoliko test tačaka — ne kao primarni izvor istine, nego kao nezavisna druga metoda da provjerimo da li se naša VISIBLE/BLOCKED odluka slaže sa Esri-jevim vlastitim viewshed alatom u istim tačkama. Ograničeno na par desetina poziva da ostane u besplatnoj zoni (50.000 elevation points/mjesec).
5. *(opciono, ako vrijeme dozvoli)* **Poređenje sa nezavisnim online viewshed alatom** (npr. heywhatsthat.com ili sličan javni servis) za par test lokacija.

Sve ovo se dokumentuje u `tests/` direktorijumu i/ili u posebnom `VALIDATION.md`, jer je upravo transparentnost oko validacije ono što ovaj MVP čini "tehnički odbranjivim" u portfolio smislu.

---

## 17. Deployment plan (provjereno protiv trenutnih uslova, ne starih informacija)

### Frontend: **GitHub Pages**
- Besplatno, HTTPS automatski (potrebno za Geolocation/Device Orientation API), custom domain podržan.
- Soft limiti: ~100 GB bandwidth/mjesec, ~1 GB veličina sajta — daleko iznad potreba portfolio demoa.
- Prirodno se uklapa u "profesionalan GitHub repo" narativ jer je deployment doslovno taj isti repo.
- Alternativa: Vercel ili Netlify (oba i dalje imaju realan besplatan tier za statički sadržaj) — biramo GitHub Pages zbog sinergije sa repo pričom, ne zato što su ostale opcije lošije.

### Backend: **Render (Free Web Service)**
- Besplatno, bez kreditne kartice, Git-based deploy (push na GitHub → automatski deploy).
- **750 besplatnih instance-sati mjesečno** — dovoljno za jedan servis koji radi 24/7 u toku razvoja/demoa.
- **Bitna karakteristika:** free web servisi "spavaju" nakon ~15 minuta neaktivnosti, buđenje traje do otprilike minut. Ovo direktno utiče na LinkedIn demo — backend treba "probuditi" (pingom na `/api/v1/health`) neposredno prije snimanja, inače prvi klik na "What am I looking at?" u videu traje neprihvatljivo dugo.
- **Railway** više nema praktično koristan besplatan tier za ovaj tip projekta (svodi se na mali jednokratni kredit, zatim usage-based naplata) — ne preporučujem ga kao primarnu opciju u 2026.
- **Fly.io** trenutno nema besplatan tier za nove korisnike (zahtijeva karticu, pay-as-you-go od starta) — ne uklapa se u "nula troškova" zahtjev.

### Zaključak
GitHub Pages + Render zadovoljavaju "skoro besplatan deployment" zahtjev bez kompromisa na HTTPS, uz jedini caveat cold-start ponašanja koje se rješava jednostavnim pre-demo pingom, ne dodatnom infrastrukturom.

---

## 18. Scope check

### MUST HAVE za MVP (v0.1)
ArcGIS mapa (Web Map + JS SDK), manual observer, manual heading, viewing sector (FOV 20–90°/radius 5–30 km kontrole), OSM `natural=peak` integracija, geodesic distance/bearing, sector/FOV filtering, DEM elevation (Copernicus GLO-30), observer elevation (DEM + eye height, bez phone fusion), target elevation (OSM `ele` → DEM fallback), line-of-sight bez curvature korekcije (scope: Srbija), visible/blocked UI, mobile geolocation, manual compass fallback (obavezan), OpenAI opis (sa graceful degradation), unit testovi za GIS matematiku, GitHub Pages + Render deployment, README.

### SHOULD HAVE (ulazi ako vrijeme dozvoli, ali ne blokira DoD)
Auto compass (device orientation) — *should*, ne *must*, jer manual mode je obavezan i dovoljan za DoD; smoothing/filtering compass signala (samo ako testiranje pokaže potrebu); debug/location-quality panel u UI-ju (backend ga svakako vraća); elevation profile u response modelu (bez chart UI-ja).

### FUTURE (eksplicitno van MVP-a, ide u README "Future Improvements")
Elevation profile chart (vizuelizacija), dodatne OSM kategorije (viewpoints, villages, lakes...), phone/DEM elevation fusion sa pravom geoid transformacijom, poboljšano compass filtriranje, varijabilna atmosferska refrakcija, 3D vizualizacija/AR camera overlay, peak prominence ranking, offline mod, sve stavke iz tvoje liste "NE RADITI U MVP-U" (native app, computer vision, user accounts, PostGIS, full raster viewshed, microservices, itd.) — ostaju eksplicitno isključene i navedene u README-u kao svjesna odluka, ne propust.

### Upozorenje na potencijalno nepotrebnu kompleksnost u onome što si stavio u MVP

Jedina stavka koju bih preispitao je **automatski compass (device orientation) kao dio v0.1 "must"** liste u tvom originalnom brifu (tačka 51, stavka 18: "compass/orientation ako je podržan"). Tehnički je "ako je podržano" već uslovno — pa ga ionako tretiram kao SHOULD HAVE, ne MUST. Ovo nije promjena scope-a, samo preciziranje da DoD (tačka 59) ne smije zavisiti od toga da compass radi na svakom test uređaju, tačno kako i sam kažeš u tački 16 ("Aplikacija ne smije zavisiti od toga da compass radi"). Sve ostalo iz tvog v0.1 scope-a je opravdano i izvodljivo u razumnom vremenu.

---

## 19. Phase 1 — status i naučene lekcije (27.09.2026)

Phase 1 (project setup + ArcGIS mapa) je implementiran i end-to-end verifikovan preko GitHub Actions CI (ne samo `py_compile`).

- **Repo:** https://github.com/mimicgoran/gis-landscape-mvp — trenutno **public**. Napomena: originalni zahtjev tokom rada je bio da repo ostane privatan dok se eksplicitno ne odobri javnost; vlasnik projekta je tokom Phase 1 rada svjesno prebacio repo na public (dva puta, uz eksplicitnu potvrdu drugi put) — ovo je zabilježeno ovdje radi transparentnosti, ne kao propust. Ako se odluka promijeni, vidljivost se mijenja iz repo Settings na GitHub-u.
- **CI:** `.github/workflows/backend-ci.yml` — na push/PR instalira `backend/requirements.txt` i pokreće `pytest tests/ -v` na GitHub-hosted Ubuntu runneru. Prvi run nakon initial push-a je prošao zeleno (svi testovi, uklj. `test_health.py` i `test_arcgis_token.py`).
- **`.env` nikad nije stigao u git** — potvrđeno i lokalnim `git status`/`git grep` pregledom prije push-a i naknadnim pregledom sadržaja repo-a preko GitHub API-ja (samo `.env.example` je prisutan).
- **Otkriveno ograničenje konektora:** GitHub MCP konektor korišten u ovoj Claude sesiji (`api.githubcopilot.com/mcp`, GitHub App "Claude Github MCP Connector") ima samo **read-only pristup javnim repo-ima** — nema instalaciju (`Installed GitHub Apps`) ni na jednom repo-u korisnika, pa write akcije (create_repository, push_files, create_or_update_file) dosljedno vraćaju `403 Resource not accessible by integration`, a read na privatnim repo-ima vraća `404` bez obzira na disconnect/reconnect ili promjenu vidljivosti repo-a. Zbog toga je initial commit/push za Phase 1 urađen lokalno: `git init`/`add`/`commit` preko veze sa korisnikovim računarom (device bridge), a stvarni `git push` je pokrenuo korisnik ručno (jedna komanda, sa svojim git kredencijalima) jer Claude sesija nema pristup korisnikovim GitHub kredencijalima. Ovo ograničenje vrijedi imati na umu za sve buduće faze: ili push ostaje ručni korak (kratak, par git komandi), ili se repo drži public da bi konektor mogao makar da čita stanje radi verifikacije.
- **GitHub Actions log čitanje:** nijedan dostupan alat u ovoj sesiji ne čita status/log GitHub Actions run-ova direktno — status se provjerava ručno na GitHub Actions tabu, ili se failed step output nalijepi nazad u chat radi popravke.
- **Vizuelna potvrda mape — uspješna, uz jedan pronađen i ispravljen bug:** lokalno pokretanje (`uvicorn` + `python -m http.server` za frontend) potvrdilo je da `/api/v1/arcgis-token` vraća pravi ArcGIS access token (empirijska potvrda cijele OAuth App authentication razmjene iz sekcije 4). Prvi pokušaj učitavanja mape je pao sa `TypeError: Cannot set properties of undefined (setting 'apiKey')` u `mapSetup.js`. Uzrok: kod je svuda pisao `esriConfig.default.apiKey`, `new GraphicsLayer.default(...)`, `new Map.default(...)`, itd. — pogrešna pretpostavka da `$arcgis.import()` vraća ES-module namespace objekat sa `.default` svojstvom. Provjereno protiv zvanične Esri dokumentacije (developers.arcgis.com, primjeri za CDN/ES-modules pristup): `$arcgis.import()` u SDK 5.1 vraća modul (klasu ili config objekat) **direktno** — ispravan obrazac je `const config = await $arcgis.import("@arcgis/core/config.js"); config.apiKey = "...";`, ne `config.default.apiKey`. Svi `.default` pozivi u `mapSetup.js` su uklonjeni; mapa se nakon toga učitava bez grešaka, centrirana na Srbiju. Sporedna napomena tokom debugovanja: browser (Chrome) je agresivno keširao stariju verziju `mapSetup.js` preko običnog refresh-a — Incognito prozor ili DevTools "Disable cache" je bio potreban da se vidi ažurirana verzija tokom razvoja preko `python -m http.server` (bez build/dev-server alata koji bi automatski invalidirao keš).
- **AGOL credit dashboard:** dashboard ima kašnjenje do 24h u prikazu potrošnje, pa provjera trenutnog basemap tile troška (sekcija 4, pretpostavka da je unutar besplatne zone) nije mogla biti odmah empirijski potvrđena — provjerava se naknadno, ne blokira dalji razvoj.

Phase 1 je zvanično završen (svi koraci iz backloga, sekcija 13, red 1, potvrđeni). Sljedeći korak: **Phase 2 — manual observer** (klik na mapu postavlja observer marker, backend `ObserverInput` model).

---

## 20. Phase 2 — status i naučene lekcije (27.09.2026)

Phase 2 (manual observer) je implementiran i verifikovan i na frontendu i na backendu.

- Klik na mapu (`observerInteraction.js`) postavlja/pomjera observer marker na `observerLayer`; prethodni marker se briše (`observerLayer.removeAll()`) prije dodavanja novog, tako da nikad ne postoji više od jednog observer markera istovremeno.
- Backend `ObserverInput` Pydantic model (`app/models/observer.py`): `latitude`/`longitude` obavezni sa range validacijom (-90/90, -180/180), `horizontal_accuracy_m`/`phone_altitude_m`/`phone_altitude_accuracy_m` opcioni (nullable) — pripremljeno za Phase 7/11 (location quality, phone altitude diagnostics), ne koriste se još.
- Minimalan debug panel (`debugPanel.js`) prikazuje lat/lon postavljenog observera — prvi korak ka punom debug/location-quality panelu iz Phase 11.
- Testovi: 7 novih unit testova (`test_observer.py`), svi prolaze lokalno i na CI-ju.
- Vizuelno potvrđeno od strane vlasnika projekta: marker se pojavljuje na tačnoj kliknutoj lokaciji, koordinate se ispisuju u debug panelu, markeri se ne gomilaju na uzastopne klikove.

Phase 2 je zvanično završen. Sljedeći korak: **Phase 3 — heading + FOV + viewing sector**.

---

## 21. Phase 3 — status i naučene lekcije (27.09.2026)

Phase 3 (heading + FOV + viewing sector) je implementiran i verifikovan i na backendu (unit testovi) i vizuelno na frontendu.

- Backend `geometry.py` (WGS84 geodesic preko `pyproj.Geod`, ne haversine/Euclidean): `geodesic_distance_km`, `initial_bearing_deg`, `angular_difference_deg`, `is_within_sector`. 13 novih unit testova (`test_geometry.py`), uključujući eksplicitni wrap-around test iz brifa (heading 359° / feature 1° → razlika 2°, ne 358°) i granični slučaj sektora (`diff == fov/2` mora biti uključeno, `<=` ne `<`). Cijeli backend test suite sada broji 25 testova, svi prolaze lokalno (`pytest tests/ -v`).
- Frontend: tri range slajdera (Heading 0–360°, FOV 20–90° default 30°, Radius 5–30 km default 5 km — pragovi obrazloženi u sekciji 8, defaulti promijenjeni u sekciji 33) u `controlsPanel.js`; sektor se crta i uživo ažurira preko `sectorGeometry.js` (čista JS sferna aproksimacija za preview, bez network round-trip-a po pokretu slajdera — izvor istine i dalje ostaje backend) i `sectorRenderer.js` (ArcGIS `Polygon`/`Graphic`).
- **Pronađen i ispravljen bug:** sektor se nije crtao na mapi iako je observer bio ispravno postavljen (marker se vidio). Uzrok: `Polygon` konstruktor u `sectorRenderer.js` je dobijao `rings` (sirovi WGS84 lon/lat parovi iz `sectorGeometry.js`) uz `spatialReference: view.spatialReference` (Web Mercator, jedinica metri). Za razliku od `Point`-a, čija `longitude`/`latitude` convenience polja uvijek pretpostavljaju WGS84 stepene i sama rade konverziju u ciljni spatialReference (zbog toga je Phase 2 observer marker sa istim obrascem radio ispravno), `Polygon.rings` se uzima doslovno kao x/y brojevi u navedenom spatialReference-u — stepeni su tako tretirani kao metri, i poligon je efektivno nestajao odmah do ishodišta Web Mercator projekcije, daleko od Srbije i van vidokruga mape. Ispravka: `spatialReference: { wkid: 4326 }` na `Polygon` konstruktoru — ArcGIS SDK automatski reprojektuje graphics između WGS84 (4326) i Web Mercator-a pri renderovanju, bez ijednog dodatnog importa. Pouka za ostatak projekta: svaka buduća geometrija konstruisana iz sirovih lon/lat parova (npr. Phase 9 visible/blocked simboli, budući elevation-profile overlay) mora eksplicitno deklarisati `{ wkid: 4326 }`, nikad `view.spatialReference`.
- Vizuelno potvrđeno od strane vlasnika projekta nakon ispravke: sektor se odmah pojavljuje na klik na mapu (poluprovidan plavi poligon), uživo se ažurira na pomjeranje bilo kog slajdera, bez gomilanja starih poligona.

Phase 3 je zvanično završen. Sljedeći korak: **Phase 4 — OSM `natural=peak` integracija** (Overpass API upit, cache, endpoint koji vraća sirove peakove u radijusu).

---

## 22. Phase 4 — status i naučene lekcije (27.09.2026)

Phase 4 (OSM `natural=peak` integracija) je implementiran i verifikovan i preko mock-ovanih unit testova i preko prave Overpass integracije.

- Backend `osm.py` (`OverpassService`): Overpass QL upit (`node["natural"="peak"](around:radius_m,lat,lon);`) preko `httpx`, in-memory TTL keš (24h, keyed po zaokruženim lat/lon/radius), defanzivan parser za OSM `ele` tag (odbacuje 0/negativne/nenumeričke vrijednosti). Privremen dev endpoint `GET /api/v1/osm/peaks` dodat radi ručne verifikacije prije nego što se poveže u finalni `/api/v1/analyze` (Phase 5-9).
- 12 novih unit testova (`test_osm.py`), svi sa mock-ovanim Overpass odgovorom (bez zavisnosti od prave mreže u CI-ju — vidi sekciju 14, rizik "Overpass reliability"). Ukupno 42 backend testa, svi prolaze.
- **Pronađen i ispravljen bug (empirijski, kroz ručno testiranje):** prvi poziv protiv prave `overpass-api.de` instance je vratio `406 Not Acceptable` (Apache default error page). Provjereno protiv zvaničnog Overpass-API GitHub issue-a (`drolbr/Overpass-API#791`) i OSM community foruma: Overpass API je 2026. uveo stroža anti-abuse pravila zbog preopterećenja servera — **zahtjevi bez identifikacionog `User-Agent` header-a se odbijaju**. Ispravka: dodat `User-Agent: GIS-Landscape-Identification-MVP/0.1 (github.com/mimicgoran/gis-landscape-mvp; ...)` header na svaki Overpass poziv, plus regresioni test koji provjerava da se header šalje. `Referer` header nije dodat (nema live domena prije Phase 15 deploymenta) — izvori navode `User-Agent` kao dovoljan fix.
- **Empirijska potvrda test lokacije (Kopaonik, sekcija 15):** nakon ispravke, `GET /api/v1/osm/peaks?lat=43.2833&lon=20.8167&radius_km=20` je vratio realnu listu vrhova (content-length ~10 KB, dvocifren broj rezultata), uključujući: Pančićev vrh (2017 m), Vučak (1936 m), Veliki Karaman (1936 m), i dalje (puna lista nije transkribovana ovdje — dostupna je ponovnim pozivom endpointa). Ovo potvrđuje da Kopaonik ima gustu, imenovanu OSM `natural=peak` pokrivenost, kako je i pretpostavljeno u sekciji 15 prije nego što su stvarni podaci bili dostupni.

Phase 4 je zvanično završen. Sljedeći korak: **Phase 5 — distance + bearing + candidate filtering** (povezivanje `geometry.py` iz Phase 3 sa stvarnim OSM peak podacima iz ove faze: distance/bearing za svaki peak, FOV/radius filter, ranking top-N kandidata).

---

## 23. Phase 5 — status i naučene lekcije (27.09.2026)

Phase 5 (distance + bearing + candidate filtering) je implementiran i verifikovan i preko unit testova i preko prave Overpass integracije.

- `geometry.py` dobija `select_candidates()`: za svaki sirov OSM peak (Phase 4) računa distance/bearing (Phase 3 funkcije), filtrira po `radius_km` i viewing sektoru, i sortira preživjele kandidate. Funkcija namjerno NE ograničava broj rezultata — capping je odgovornost pozivaoca.
- **Rangiranje (dizajn odluka, obrazložena prije implementacije):** prvo po ugaonoj blizini heading-u (`angular_difference_deg` rastuće — najrelevantniji odgovor na "šta gledam"), pa po `distance_km` kao tiebreaker. Elevation/prominenca namjerno NE ulazi u rangiranje u ovoj fazi — DEM (Phase 6) i pouzdana OSM `ele` pokrivenost još nisu dostupni za sve kandidate, pa bi to bila neopravdana heuristika (isti princip kao odluka o elevation fusion-u, sekcija 6).
- `Settings.candidate_ranking_max_n = 20` — cap na broj kandidata koji idu dalje u DEM/line-of-sight (Phase 6-8), obrazložen brifom (tačka 44: "10-20") i empirijski (Kopaonik gustina vrhova, sekcija 22).
- Novi dev endpoint `GET /api/v1/osm/candidates` (heading/FOV/radius parametri) vraća `{"candidates": [...], "debug": {...}}` — `debug` blok prati oblik iz sekcije 11 (finalni `/api/v1/analyze`).
- 7 novih testova (5 u `test_geometry.py` za `select_candidates`, uključujući eksplicitan wrap-around slučaj; 2 endpoint-level u `test_osm.py`). Ukupno 49 backend testova, svi prolaze.
- **Empirijska potvrda:** poziv `/api/v1/osm/candidates` protiv prave Overpass instance za Kopaonik (`heading_deg=90, fov_deg=45, radius_km=20`) je nakon par retry-ja (vidi ispod) vratio manju, filtriranu listu kandidata sa ispravnim `debug` brojevima.
- **Napomena (ne bug, već potvrda već dokumentovanog rizika):** tokom ručne provjere, Overpass API je vratio `504 Gateway Timeout` (naš servis je to ispravno propagirao kao `503`, bez pada aplikacije). Ovo je tačno rizik već naveden u sekciji 14 ("Overpass reliability — LOW-MEDIUM, javne instance mogu biti spore ili privremeno vratiti 429/504"). Riješeno prostim retry-jem (2 pokušaja) — ako se ovo pokaže učestalim tokom daljeg razvoja/demoa, razmotriti fallback na alternativnu javnu instancu (`overpass.kumi.systems`) u `Settings.overpass_api_url`.

Phase 5 je zvanično završen. Sljedeći korak: **Phase 6 — DEM integracija** (Copernicus DEM GLO-30 preko `rasterio`, S3 COG windowed read, lokalni disk cache tile-ova — vidi sekciju 5).

---

## 24. Phase 6 — status i naučene lekcije (27.09.2026)

Phase 6 (DEM integracija) je implementiran i verifikovan i preko unit testova i preko prave Copernicus DEM GLO-30 integracije, ali uz jednu značajnu arhitekturnu izmjenu u odnosu na originalni plan (obrazloženo ispod).

- **Arhitekturna izmjena: "download-once, cache-on-disk" umjesto GDAL `/vsicurl/` streaming reada.** Originalni DEM strategy plan (sekcija 5) je predviđao da `rasterio` čita direktno sa udaljenog COG-a preko GDAL-ovog `/vsicurl/` virtuelnog filesystema (HTTP range reads, bez punog preuzimanja tile-a). Empirijski je utvrđeno da SVAKI pokušaj otvaranja `/vsicurl/https://...tif` baca `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 ...`, nezavisno od isprobanih GDAL config opcija (`GDAL_DISABLE_READDIR_ON_OPEN`, `CPL_VSIL_CURL_ALLOWED_EXTENSIONS`, `CPL_LOG` redirekcija). Uzrok, potvrđen čitanjem rasterio-ovog izvornog koda (`_err.pyx`): `# cython: c_string_encoding=utf8` direktiva ugrađena u kompajliranu binarnu ekstenziju prisiljava striktno UTF-8 dekodiranje GDAL log/error stringova prije prosljeđivanja Python logging sloju; jedan od CURL debug logova koje `/vsicurl/` generiše sadrži bajt koji nije validan UTF-8. Ovo se ne može zaobići ni na jedan način dostupan iz Python koda (nije env varijabla, nije logging konfiguracija) — fix bi zahtijevao rekompajliranje rasteria iz izvora, što je van razumnog scope-a MVP-a. **Odluka:** tile (1×1° COG, ~40-45 MB) se preuzima JEDNOM preko običnog `httpx` HTTP GET-a na lokalni disk (`app/data/dem_cache/`, gitignored), keširan po imenu tile-a; svako sledeće čitanje ide protiv te lokalne kopije. Tradeoff: prvi zahtjev za novu geografsku oblast je sporiji (par sekundi do minut preuzimanja umjesto par range-readova od par KB), ali za MVP sa nekoliko test lokacija (Kopaonik, Stara planina, Tara) ovo je jednostavnije i u praksi brže nakon prvog poziva. Ovo je svjestan kompromis u skladu sa principom "jednostavnije rešenje koje dovoljno dobro demonstrira koncept" (brief, uvod).
- **Usput pronađen i ispravljen nezavisan bug: PROJ_LIB/PostGIS konflikt.** Na razvojnoj mašini je lokalna PostgreSQL/PostGIS instalacija postavila mašinski `PROJ_LIB` env var koji pokazuje na stariju, nekompatibilnu `proj.db` bazu — `rasterio`/`pyproj` (instalirani preko pip-a) su je pokupili umjesto svoje bundlovane verzije, što je bacalo `rasterio.errors.CRSError: ... DATABASE.LAYOUT.VERSION.MINOR = 2 ...` čak i pri otvaranju običnog lokalnog GeoTIFF-a. Ispravka (potvrđena protiv rasterio FAQ-a i GitHub Discussion #2721 sa identičnim slučajem): `os.environ.pop("PROJ_LIB", None)` i `os.environ.pop("PROJ_DATA", None)` na vrhu `elevation.py` modula, PRIJE `import rasterio` — rasterio se tad vraća na sopstvenu bundlovanu PROJ verziju. Ovaj bug je nezavisan od `/vsicurl/` problema (oba su morala biti riješena odvojeno) i vjerovatno je specifičan za ovu razvojnu mašinu (bilo koja instalacija sa konfliktnim sistemskim `PROJ_LIB`-om bi imala isti problem) — vrijedi napomenuti u README Limitations sekciji za buduće contributore (Phase 16).
- **Pokrivenost potvrđena za Srbiju/Kopaonik.** AWS Open Data Registry dokumentacija za Copernicus GLO-30 Public navodi "limited worldwide coverage" (neki tile-ovi nisu objavljeni) — ovo NIJE bilo moguće potvrditi/opovrgnuti za Srbiju istraživanjem unaprijed. Direktan HTTP GET protiv `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N43_00_E020_00_DEM/...tif` je vratio stvarni TIFF (43.721.301 bajtova) — Kopaonik/Srbija JESU pokriveni.
- **Empirijska tačnost:** DEM elevacija na koordinatama Pančićevog vrha (43.2692547, 20.8236633) je **2011.63 m**, naspram OSM `ele` taga od **2017 m** — razlika ~5.4 m. Ovo je u granicama očekivanog, NE ukazuje na grešku: GLO-30 ima deklarisanu vertikalnu tačnost reda veličine nekoliko metara (RMSE), OSM čvor za vrh nije nužno na geodetski najvišoj tački piksela, a 30 m horizontalna rezolucija znači da je uzorkovana vrijednost efektivno prosjek terena na tom pikselu (vidi i sekciju 26 brief-a: 30 m horizontalna rezolucija ≠ ±30 m vertikalna greška).
- `app/services/elevation.py`: `ElevationService.get_elevation(lat, lon) -> float | None` — računa naziv tile-a (`_tile_name`, SW-corner konvencija, potvrđena empirijski za N/E hemisferu, generalizovana ali NE empirijski testirana za S/W jer su sve test lokacije na Balkanu), preuzima ga ako nije keširan (`_download_tile`, atomski preko privremenog `.part` fajla da keš nikad ne sadrži polovičan/oštećen download), otvara lokalnu kopiju sa `rasterio` i uzorkuje elevaciju. Vraća `None` (ne baca exception) za sve neuspješne slučajeve — tile van pokrivenosti (404), mrežni problem pri preuzimanju, ili "nodata" piksel — namjerno bez razlikovanja između njih, jer pozivalac (Phase 7 location quality logika) u sva tri slučaja treba isto: tretirati DEM kao nedostupan i nastaviti dalje (brief, tačka 42).
- Novi dev endpoint `GET /api/v1/elevation/lookup?lat=&lon=` (sync `def`, ne `async def` — FastAPI automatski pokreće blokirajuće sync rute u threadpool-u, dovoljno za MVP saobraćaj bez dodatne async komplikacije oko `rasterio`/`httpx.Client`, koji su i dalje sinhroni).
- 13 novih testova (`test_elevation.py`): `_tile_name` za sve 4 kombinacije hemisfera, cache-hit vs. download put, "nodata" piksel, graceful `None` kad preuzimanje ne uspije, i endpoint-level testovi. Mrežni download je svuda mock-ovan (CI ne smije zavisiti od Copernicus S3 dostupnosti), ali stvarno `rasterio` čitanje/sampling se NE mock-uje — testovi pišu pravi mali GeoTIFF fixture na disk, čime se prava logika (nodata handling, cache-hit put) i dalje testira. Ukupno 62 backend testa, svi prolaze.
- Vizuelno/ručno potvrđeno od strane vlasnika projekta preko Swagger UI-ja: `GET /api/v1/elevation/lookup?lat=43.2692547&lon=20.8236633` vraća `{"elevation_m": 2011.6337890625, "elevation_source": "dem"}` — identično dijagnostičkom skriptu korišćenom tokom troubleshooting-a.

Phase 6 je zvanično završen. Sljedeći korak: **Phase 7 — observer elevation + location quality arhitektura** (spajanje DEM elevacije sa phone altitude/accuracy signalima iz brief-a, sekcije 9-14: prag za location quality HIGH/MEDIUM/LOW, prag za phone altitude accuracy koji odlučuje da li phone altitude uopšte učestvuje, i weighted fusion model — sve uz prethodno predlaganje i obrazloženje pragova, ne proizvoljno hardkodovanje).

---

## 25. Phase 7 — status i naučene lekcije (27.09.2026)

Phase 7 (observer elevation + location quality arhitektura) je implementiran i verifikovan i preko unit testova i ručno preko dev endpointa. Za razliku od prethodnih faza, ovdje nije bilo novih tehničkih iznenađenja -- glavna logika (DEM kao jedini autoritativni izvor, phone altitude dijagnostika bez fuzije, pragovi za confidence) je već bila predložena i odobrena u sekciji 6, prije bilo kakve implementacije. Phase 7 je dodao dva granična slučaja koja sekcija 6 nije eksplicitno pokrivala, predložena i odobrena PRIJE pisanja koda:

- **DEM nedostupan za observer lokaciju** (van GLO-30 pokrivenosti ili mrežni problem) → `confidence` je automatski `"low"`, bez obzira na GPS `horizontal_accuracy_m`, i `selected_ground_elevation_m`/`elevation_source` ostaju `None`. Vlasnik projekta je primijetio da će za sve stvarne test lokacije (Kopaonik, Stara planina, Tara — sve u Srbiji, pokrivenost već potvrđena u Phase 6) DEM praktično uvijek biti dostupan — ova grana koda je zato više odbrana za produkcijsku robusnost/portfolio kvalitet nego stvarno očekivan scenario u demou, ali je zadržana jer `ElevationService.get_elevation()` (Phase 6) već vraća `None` besplatno u tom slučaju, pa ignorisanje te informacije ne bi imalo smisla.
- **`horizontal_accuracy_m is None`** (manual/desktop observer, Phase 2 — klik na mapu nema GPS accuracy koncept) → tretira se kao `"high"`, ne kao nepoznato/`"low"`. Obrazloženje: manuelni klik je namjerno, tačno postavljena tačka bez GPS greške, ne "GPS fix nepoznate preciznosti" — tretiranje kao `"low"` bi neopravdano obezvrijedilo svaki desktop-development test (brief, tačka 38).

- `app/models/location_quality.py`: `LocationQuality` Pydantic model, tačno prema JSON šemi već definisanoj u sekciji 11 (`horizontal_accuracy_m`, `phone_altitude_m`, `phone_altitude_accuracy_m`, `dem_elevation_m`, `selected_ground_elevation_m`, `elevation_source`, `confidence`). `elevation_source` tipiziran kao `Literal["dem", "dem_phone_fusion", "dem_phone_disagreement"] | None` — potonja dva su dio šeme radi buduće kompatibilnosti (Phase 2/Future fuzija), ali logika koja bi ih aktivno postavljala nije implementirana u MVP-u (vidi sekciju 6).
- `app/services/location_quality.py`: `classify_confidence()` (čista funkcija, pragovi iz `Settings` + oba granična slučaja iznad), `compute_observer_elevation_m()` (`terrain_elevation + eye_height`, `None` ako terrain nedostupan), `build_location_quality()` (sastavlja pun model; `selected_ground_elevation_m` je u MVP-u uvijek == `dem_elevation_m`, pošto fuzija nije implementirana).
- Novi dev endpoint `GET /api/v1/observer/elevation` (lat/lon + opcioni horizontal_accuracy_m/phone_altitude_m/phone_altitude_accuracy_m) kombinuje Phase 6 `ElevationService` sa Phase 7 servisom i vraća pun `observer`/`location_quality` pregled iz sekcije 11, kao pripremu za `/api/v1/analyze` (Phase 9).
- 15 novih testova (`test_location_quality.py`): granični slučajevi pragova (tačno na `horizontal_accuracy_high_m`/`horizontal_accuracy_medium_m`, taman iznad), `None` accuracy → `"high"`, DEM nedostupan → `"low"` bez obzira na accuracy (uklj. kombinaciju sa `None` accuracy), sastavljanje modela, endpoint-level testovi. Ukupno 77 backend testova, svi prolaze.
- Ručno potvrđeno preko Swagger UI-ja za Pančićev vrh (43.2692547, 20.8236633): sa `horizontal_accuracy_m=6.4` → `observer_elevation_m: 2013.3337890625` (DEM 2011.6337890625 + eye height 1.7), `confidence: "high"`, `elevation_source: "dem"`; bez `horizontal_accuracy_m` (manual observer slučaj) → identičan `observer_elevation_m`, `confidence` ostaje `"high"`.

Phase 7 je zvanično završen. Sljedeći korak: **Phase 8 — line-of-sight engine** (za svaki kandidat iz Phase 5, geodesic linija observer→target, DEM sampling duž linije po pravilima iz sekcije 9, elevation angle poređenje, visible/blocked odluka).

---

## 26. Phase 8 — status i naučene lekcije (27.09.2026), plus automatski Overpass retry

Phase 8 (line-of-sight engine) je implementiran i end-to-end testiran: 96 backend testova prolazi, i vlasnik projekta je ručno potvrdio pun pipeline (observer → OSM kandidati → DEM → line-of-sight) protiv prave Kopaonik lokacije preko `/api/v1/analyze/preview` -- rezultat je bio plauzibilan (razumna podjela na `visible_features`/`blocked_features`), nakon jednog tranzitornog Overpass `503` koji je uspio na ručni retry.

- **Batch DEM sampling** (`ElevationService.get_elevation_profile()`) -- grupiše sample tačke po tile-u i otvara svaki `rasterio` dataset TAČNO JEDNOM, ne po tački. Bitno jer jedna 30 km line-of-sight provjera zahtijeva i do ~1000 sample tačaka -- otvaranje fajla po tački bi bilo neprihvatljivo sporo.
- **Sample tačke duž linije**: `geometry.geodesic_intermediate_points()` preko `pyproj.Geod.npts()`, na `Settings.line_of_sight_sample_spacing_m` (30 m, = DEM rezolucija) razmaku, BEZ krajnjih tačaka (observer/target se tretiraju odvojeno).
- **Granični slučaj (dogovoren prije implementacije):** terenska tačka blokira target samo ako joj je elevation angle STROGO veći (`>`, ne `>=`) od target ugla -- tačka na istom uglu dodiruje liniju posmatranja tačno na nivou cilja, nije stvarna prepreka.
- **"DEM gap"** (terenska tačka bez dostupne elevacije) se NE tretira kao blokada niti kao greška -- preskače se u max-angle računu, `dem_gap=True` transparentno signalizira nepotpun profil (isti princip kao `location_quality`, Phase 7).
- **Target elevation prioritet:** OSM `ele` kad postoji, DEM kao fallback; razlika preko `Settings.target_elevation_discrepancy_threshold_m` (50 m -- DEM ima tendenciju blagog potcjenjivanja pravog vrha zbog 30 m usrednjavanja piksela) se SAMO bilježi (`elevation_discrepancy_m`), nikad ne mijenja izabrani izvor.
- Novi dev endpoint `GET /api/v1/analyze/preview` -- puni pipeline, sync `def` (rasterio/httpx su blokirajući), Overpass poziv preko `asyncio.run()` unutar threadpool thread-a.
- **Automatski Overpass retry** (dodano nakon prvog ručnog testa, kao direktna reakcija na stvarno viđen `503`): `Settings.overpass_max_retries=2`, `overpass_retry_backoff_s=2.0`, `_TRANSIENT_STATUS_CODES={429,502,503,504}` -- isti princip u oba Overpass servisa (tačkasti i, od Phase 9, area feature-i). Trajne greške (npr. 400) se NE retry-uju -- odmah se odustaje. **Potvrđeno:** korisnik je pokrenuo pun `pytest tests/ -v` nakon Phase 8+9 izmjena -- **148 passed, 0 failed** (uključuje i retry testove).

Phase 8 je funkcionalno završen i potpuno verifikovan (148 testova + ručni end-to-end test preko `/api/v1/analyze/preview` protiv prave Kopaonik lokacije, uključujući ručnu provjeru terrain profila -- vidi sekciju 27 ispod za detalje te provjere).

---

## 27. Phase 9 — status i naučene lekcije (27.09.2026): proširenje sa "samo vrhovi" na "sve geografske odrednice bez ulica"

Neposredno nakon Phase 8 verifikacije, vlasnik projekta je eksplicitno odbacio ideju da aplikacija ostane ograničena na planinske vrhove: korisnik postavlja i pitanja poput "koja je rijeka preko puta mene", "koje je mjesto preko puta", "koji je park ispred mene" -- zahtjev je bio da se pokriju SVI geografski OSM elementi OSIM ulica ("sve ostale geografske odrednice jesu potrebne"). Kroz tri kruga prijedlog→korekcija (svaki krug je otkrio stvaran tehnički nedostatak prethodnog prijedloga, ne stilsku primjedbu), scope je sveden na tehnički izvodljiv, i dalje MVP-portfolio-veličine, presjek:

- **Tačkasti feature-i** (isti pipeline kao vrhovi, Phase 4-8, samo dodato `category` polje): `place=city|town|village` (naselja) i `tourism=viewpoint` (vidikovci), pored postojećeg `natural=peak`.
- **Area feature-i** (NOVI pipeline, sector-intersect + "mini-viewshed", vidi ispod): `waterway=river` (rijeke), `natural=water` (sve vodene površine -- eksplicitan zahtjev "trebaju mi sve vodene površine"), `leisure=park` (parkovi), `boundary=national_park` (nacionalni parkovi).
- Van scope-a i dalje ostaje: sve što je vezano za ulice/saobraćajnice (`highway=*`) -- eksplicitno isključeno na zahtjev korisnika ("to mi stvarno nije potrebno").

### Zašto NIJE centroid-only pristup (dva kruga korisničke korekcije)

Prvi prijedlog je bio uzeti `out center;` (Overpass centroid) za rijeke/parkove/vodene površine i porediti SAMO tu jednu tačku sa sektorom -- korisnik je ovo eksplicitno odbio ("ovo nije dobar princip") jer feature sa protežnošću može imati centroid VAN sektora dok mu je STVARNI dio (npr. bliža obala) UNUTAR sektora -- centroid-only bi takav feature lažno izostavio iz rezultata. Drugi krug iste greške, sitnija varijanta: pojednostavljen tretman OSM **relacija** (npr. `boundary=national_park`) preko centroida CIJELE relacije -- korisnik je i ovo odbio istim argumentom ("centroid cijele relacije nije dobar pristup... ako sektor pokriva dio poligona a ne njegov centroid, korisnik neće dobiti informaciju da je to Nacionalni park Kopaonik"). Konačno rješenje: relacije dobijaju ISTI pun tretman kao way objekti (nema više posebnog slučaja) -- vidi "Relation → Polygon" ispod.

Korisnik je zatim, kroz `AskUserQuestion`, eksplicitno izabrao najzahtjevniju od tri ponuđene opcije za samu visibility provjeru: **"više tačaka duž isječka (mini-viewshed po feature-u)"**, umjesto jedne reprezentativne tačke ili potpunog izostavljanja visibility provjere za area feature-e. Ovo je namjerno svjesno demandingnija opcija od minimalno potrebne -- prihvaćena uz eksplicitno upozorenje da je ograničena (fiksni mali broj sample-ova po feature-u), NIJE puni raster viewshed (brief, tačka 52, i dalje eksplicitno isključen).

### Novi pipeline za area feature-e

1. **`OverpassAreaService`** (`app/services/osm_areas.py`) -- union Overpass upit za sve četiri kategorije, `out geom;` za punu geometriju. Way → `LineString` (nezatvoren, npr. rijeka) ili `Polygon` (zatvoren prsten). Relation → `Polygon`/`MultiPolygon` preko `shapely.ops.polygonize()` nad `role="outer"` way-ovima (role="inner", tj. rupe/enklave, se IGNORIŠU -- dogovorena pojednostavljenja, dokumentovana granica MVP-a).
2. **`geometry.build_sector_polygon()`** -- viewing sector kao Shapely `Polygon` (wedge), konstruisan preko `Geod.fwd()` za tačke duž luka na `radius_km`. NAMJERNO u sirovim WGS84 stepenima (bez reprojekcije u metrički CRS) -- na skali do 30 km distorzija je zanemarljiva za topološki intersect (ne mjerenje -- sve stvarne distance/bearing i dalje idu preko `pyproj.Geod`).
3. **`area_visibility.intersect_with_sector()`** -- stvaran geometrijski `shapely` intersect feature geometrije sa sector poligonom (zamjena za odbačeni centroid pristup). Feature van sektora → potpuno izostavljen iz rezultata.
4. **Sample tačke duž presječenog dijela** -- linija: duž same linije (`LineString.interpolate()`); poligon: grid UNUTAR presječene površine (ne duž konture, jer kontura presječenog poligona dijelom prati IVICE SAMOG SEKTORA, ne stvarnu granicu feature-a). Spacing (`Settings.area_feature_sample_spacing_m = 200 m`) je namjerno KRUPNIJI od line-of-sight DEM sampling-a (30 m) -- ovdje su sample tačke SAME targeti (svaka pokreće punu `check_visibility()` provjeru), ne teren između, pa gušće sample-ovanje samo umnožava trošak bez proporcionalne koristi. Broj sample-ova je ograničen (`Settings.area_feature_max_samples_per_feature = 12`, ravnomjerno prorijeđeno ako ih ima više).
5. **Agregacija** -- ISTA `check_visibility()` funkcija (Phase 8, nepromijenjena) po sample tački; `visible_fraction = visible_sample_count / (sample_count - dem_gap_sample_count)`; `visibility` klasifikovan kao `"visible"` (frakcija 1.0), `"partially_visible"` (0 < frakcija < 1.0), ili `"blocked"` (frakcija 0.0). Sample tačke bez DEM-a se izuzimaju iz imenioca (isti "DEM gap" princip kao Phase 8) -- ako NIJEDNA sample tačka nema DEM, feature se u potpunosti izostavlja (ne izmišlja se vidljivost).
6. Novi model `AnalyzedAreaFeature` (`app/models/feature.py`) i novi `"area_features"` ključ u `/api/v1/analyze/preview` odgovoru, sortiran po `closest_distance_km`, ograničen na `Settings.area_feature_max_results = 15`.

### Ostale odluke

- **Koordinatna konvencija:** sve Shapely geometrije u ovom projektu koriste `(longitude, latitude)` red (Shapely/GeoJSON standard), NE `(lat, lon)` kako OSM/Overpass imenuje polja -- eksplicitno komentarisano i testirano na više mjesta (`test_osm_areas.py::test_way_geometry_uses_lon_lat_order`) jer je zamjena redosleda čest izvor tihih bugova.
- **Rename zbog proširenog scope-a:** `OSMPeak`→`OSMPointFeature`, `PeakCandidate`→`PointCandidate` (dodato `category: "peak"|"settlement"|"viewpoint"`), `fetch_peaks_in_radius`→`fetch_point_features_in_radius`. Dev endpointi preimenovani: `/osm/peaks`→`/osm/points`, `/osm/candidates`→`/osm/point-candidates`; dodat `/osm/areas` (sirova area geometrija, GeoJSON-oblik, radi ručne provjere PRIJE sector-intersect/sampling sloja).
- **Pronađen i ispravljen bug prije bilo kakvog testiranja od strane korisnika** (samo-provjera koda prije predaje): `shapely.ops.nearest_points(g1, g2)` vraća `(tačka_na_g1, tačka_na_g2)` -- u prvoj verziji `area_visibility.py` je tuple raspakovan obrnuto (`nearest_on_feature, _ = nearest_points(observer_point, feature.geometry)`), što bi tiho vratilo `closest_distance_km=0` za SVAKI area feature. Uočeno ručnom provjerom logike prije predaje testova, ispravljeno (`_, nearest_on_feature = ...`), sa eksplicitnim komentarom u kodu protiv regresije.

### Pretpostavka o Overpass `out geom;` na relacijama -- EMPIRIJSKI POTVRĐENA

Cijeli area-feature pipeline pretpostavlja da Overpass `out geom;` ugrađuje PUNU geometriju svakog člana relacije direktno u `element["members"][i]["geometry"]` (dokumentovano, standardno Overpass ponašanje -- isti pristup koristi npr. overpass-turbo). Ova pretpostavka NIJE mogla biti testirana iz razvojnog okruženja (i cloud sandbox i lokalna bridge VM imaju egress politiku koja blokira `overpass-api.de`, potvrđeno direktnim `curl` pokušajem u oba), pa je ostala eksplicitno označena kao neprovjerena do prve ručne provjere.

**Potvrđeno ručnom Swagger provjerom** (`GET /api/v1/osm/areas`, lat=43.2833/lon=20.8167, radius=30 km): relacija `osm_id=9499191` ("Национални парк Копаоник", `category: national_park`) je ispravno sastavljena u validan, veliki, ne-degenerisan `Polygon` (nekoliko stotina koordinatnih parova, prostorno smislena kontura Kopaonik masiva). Dodatno potvrđeno na još dvije relacije u istom odgovoru: `5969844` ("Рекреациони центар", `park`) i `18185060` (`water`) -- obje takođe validni poligoni. `shapely.ops.polygonize()` nad `role="outer"` member way-ovima iz `out geom;` odgovora dakle radi ispravno na realnim OSM podacima, ne samo na sintetičkim test fixture-ima.

### Status testiranja -- VERIFIKOVANO

Cijeli Phase 9 kod (`osm_areas.py`, `area_visibility.py`, `build_sector_polygon`, rename, novi modeli/config) je prošao kompletan ciklus provjere:

1. **`pytest tests/ -v`** -- **148 passed, 0 failed** (uključuje `test_osm_areas.py`, `test_area_visibility.py`, i sve proširene testove).
2. **`GET /api/v1/osm/areas`** -- ručno potvrđeno na Kopaoniku (vidi gore) da way geometrija (rijeke kao `LineString`) i relation geometrija (nacionalni park/park/water kao `Polygon`) ispravno rade na živim podacima.
3. **`GET /api/v1/analyze/preview`** (lat=43.2833, lon=20.8167, heading=270, fov=60) -- pun end-to-end poziv (point + area feature-i zajedno) vraćen je i pregledan. Prvi rezultat (radius=20 km) je pokazao **0 vidljivih od 35 analiziranih feature-a** (i tačkastih i area), što je inicijalno djelovalo sumnjivo -- umjesto da se to protumači kao "izgleda plauzibilno" bez provjere, zatražen je isti poziv sa `include_profile=true` i manjim radius-om (5 km) radi uvida u stvarne DEM terrain profile.

   **Ručna provjera terrain profila** (distance/elevation parovi duž linije observer→target) je potvrdila da je "sve blokirano" ISPRAVAN rezultat za baš tu tačku posmatranja, ne bug: posmatrač (1770.3 m) stoji na padini/terasi Kopaonika, ne na samom vrhu, i ima stvarnu bližu uzvišicu (~800 m dalje, DEM ~1789 m -- viša od same posmatračeve elevacije) koja mu zaklanja skoro cijeli zapadni sektor (240°-300°). Ručni preračun ugla (`atan2`) za dva "Три клупе" vidikovca i naselje "Копаоник" se poklopio sa algoritamskom `blocked` odlukom u sva tri slučaja (uključujući jedan granični slučaj sa razlikom uglova od svega ~0.08°, što je razumno na 30 m DEM rezoluciji). DEM kriva je pritom bila glatka i kontinuirana, bez skokova ili očigledno pogrešnih vrijednosti -- što isključuje sumnju na loš elevation servis ili DEM sampling grešku.

   Zaključak: Phase 8 `check_visibility()` logika (i, preko iste funkcije, Phase 9 mini-viewshed agregacija) je verifikovana ne samo testovima nego i ručnom provjerom stvarne matematike protiv stvarnog terena -- ovo je bio potreban korak jer test fixture-i (mock elevation servisi) ne mogu otkriti sistematsku grešku u pravim DEM podacima, samo u logici poređenja.

Phase 8 + Phase 9 su spremni za commit/push (zajedno, vidi sekciju 26).

---

## 28. Phase 10 (frontend) -- otkriven procjep u numeraciji faza, i rezultati UI + mobile geolocation zajedno (28.09.2026)

Prije implementacije ovog koraka, provjeren je stvaran stanje frontend koda (ne pretpostavljeno) -- otkriveno je da frontend stoji na nivou originalnog brief Phase 3 (mapa + manual observer + heading/FOV/radius kontrole + sektor), bez ijedne linije koda koja poziva `/api/v1/analyze` ili prikazuje rezultate. **Uzrok:** originalni brief (sekcija 54) ima Phase 9 = "Visible/blocked UI" kao zaseban frontend korak, ali kad je korisnik odmah nakon backend Phase 8 zatražio prošireni OSM scope (rijeke/vode/parkovi), taj rad je hronološki dobio ime "Phase 9" u ovom projektu -- originalni frontend Phase 9 je time tiho ostao neurađen, prekriven drugačijim radom pod istim brojem. Ovo je eksplicitno prijavljeno korisniku prije pisanja koda (ne prećutano), koji je odlučio da se preostali frontend rad -- rezultati UI (originalni Phase 9) i mobile geolocation (Phase 10) -- uradi ZAJEDNO, kao jedna faza, umjesto odvojeno, jer geolocation sam za sebe ne daje vidljivu vrijednost bez načina da se rezultat analize prikaže.

### Odluke prije implementacije (potvrđene sa korisnikom)

1. **Geolocation gesture-triggered, ne automatski na page load** -- traži se tek na klik dugmeta "Koristi moju lokaciju" (`services/geolocationService.js`). Pouzdanije na iOS Safari, manje nametljivo.
2. **Jednokratno očitavanje (`getCurrentPosition`), ne `watchPosition`** -- dovoljno za scenario "stojim na vidikovcu" (brief tačka 1); kontinuirano praćenje eksplicitno odloženo za Future ako se pokaže potreba.
3. **Location-quality debug panel uključen odmah** (ne odložen u Future, iako je brief tačka 15 to dozvoljavao) -- backend je već vraćao sve potrebne podatke (`location_quality`, `debug` blok) od Phase 7/8, pa je prikaz na frontendu mala nadogradnja, ne novi scope.

### API kompromis (dokumentovan, ne prećutan)

Frontend (`services/analyzeService.js`) poziva postojeći `GET /api/v1/analyze/preview` (query parametri), IAKO je taj endpoint u svom docstringu najavljivao da će "finalni" oblik biti `POST /api/v1/analyze` sa observer objektom u body-ju. Odlučeno je da se ta REST-čistoća odloži -- trenutni GET oblik već potpuno pokriva frontend potrebe, i promjena ugovora bi u ovom trenutku bila čisto kozmetička. Prirodna prilika da se to ipak uradi: Phase 13 (OpenAI sloj), kad endpoint svakako mora da se promijeni da doda `ai_description`.

### Šta je urađeno

- **`services/geolocationService.js`** (nov) -- Promise wrapper oko `navigator.geolocation.getCurrentPosition()`, sa čitljivim porukama za sva tri `GeolocationPositionError` koda (permission denied / position unavailable / timeout) i za nedostupan secure context (HTTP na LAN IP -- poznato ograničenje do Phase 15 HTTPS deploymenta).
- **`services/analyzeService.js`** (nov) -- poziva `/api/v1/analyze/preview`, tretira `debug.error` (DEM nedostupan) kao grešku na frontend strani, ne kao "prazan rezultat".
- **`map/observerInteraction.js`** (refaktorisan) -- `placeObserverMarker()` izdvojen kao zajednička putanja za manual klik I geolocation (ista Point/Graphic/symbol logika, bez duplikacije).
- **`map/symbols.js`** (dopunjen) -- `createVisibleFeatureSymbol()` (zelen, upadljiviji) i `createBlockedFeatureSymbol()` (sivo, prigušeno) -- brief tačka 35: visible mora biti vizuelno važniji.
- **`map/resultsRenderer.js`** (nov) -- crta visible/blocked TAČKASTE feature-e na `resultsLayer` (koji je postojao od Phase 1 ali bio nekorišten), sa popup-ima. Area feature-i (rijeke/vode/parkovi) se NAMJERNO ne crtaju kao geometrija ovdje -- `AnalyzedAreaFeature` ne nosi koordinate (samo distancu/bearing do najbliže tačke), da se ne bi duplirala puna Overpass geometrija u dva odgovora. Prikazuju se samo tekstualno u `resultsPanel.js`. Crtanje njihove stvarne geometrije na mapi je Future stavka.
- **`ui/resultsPanel.js`** (nov) -- lista visible/blocked tačaka (visible prvo) i area feature-a, sa bedževima (VIDLJIVO/ZAKLONJENO/DJELIMIČNO). Prost DOM, bez frameworka (brief tačka 35).
- **`ui/actionButtons.js`** (nov) -- "Koristi moju lokaciju" i "Šta gledam?" dugmad, sa loading stanjima.
- **`ui/debugPanel.js`** (prošireno) -- kolabsiran po defaultu (brief sekcija 15), expand prikazuje pun `location_quality` + `debug` blok (GPS accuracy, phone altitude/accuracy, DEM elevation, observer elevation, elevation_source, heading/FOV/radius, OSM candidate counts) -- brief sekcija 57 zahtjevi, skoro svi podaci već postojali u backend odgovoru.
- **`main.js`** (prepisan) -- orkestracija: observer (klik ILI geolocation) -> `renderSector` (postojeće) -> na klik "Šta gledam?" -> `fetchAnalysis` -> `debugPanel.updateAnalysis` + `resultsPanel.render` + `renderResults` (mapa). Stari rezultati se brišu čim se observer pomjeri (novi klik/geolocation), da ne zavaravaju korisnika dok se analiza ponovo ne pokrene.
- **`index.html` / `styles/main.css`** -- novi `#actionBar` (top-left), `#resultsPanel` (bottom-right, scroll, max-height), mobile-first media query na 480px (action bar/controls dijele širinu, results panel puna širina).

### Status testiranja

Sav novi/izmijenjeni JS kod je provjeren preko `node --check` (sintaksna validacija -- nema browser/DOM okruženje u dev sandbox-u da se izvrši stvarni end-to-end test). **Korisnička ručna provjera u browseru (klik na mapu, geolocation dugme, "Šta gledam?" dugme, provjera rezultata/debug panela na desktopu i telefonu) JOŠ NIJE urađena** -- ovo je "implementirano, čeka verifikaciju", isti princip transparentnosti kao Phase 9 prije svoje verifikacije (sekcija 27). Poznato ograničenje za testiranje sa telefona: geolocation zahtijeva HTTPS ili localhost, pa testiranje preko LAN IP-a (telefon -> desktop dev server) neće raditi za geolocation dio (manual klik i dalje radi) -- rješava se tek u Phase 15 (HTTPS deployment) ili privremenim HTTPS tunelom (npr. ngrok) ako se želi testirati geolocation prije toga.

## 29. Prvi ručni test Phase 10 UI-ja (Sava kod Orašca) -- dva otvorena pitanja (28.09.2026)

Korisnik je ručno testirao Phase 10 UI (klik na mapu pored Save, "Šta gledam?") i prijavio dva neočekivana rezultata, umjesto da se rezultat prihvati na oko:

1. **Dupli rezultati za istu rijeku:** i "Vodena površina" (category `water`, bez imena) i "Сава" (category `river`, sa imenom) su se pojavili kao DVA odvojena rezultata na skoro istoj poziciji/distanci. **Uzrok (potvrđen, ne pretpostavka):** ovo je stvarna OSM konvencija, ne bug -- veće rijeke poput Save se u OSM-u tipično mapiraju NA OBA NAČINA istovremeno: `waterway=river` linija (centralna linija toka, obično nosi `name` tag) I `natural=water` poligon (stvarna vodena površina obala-do-obale, često BEZ `name` taga). Ovo su dva različita OSM elementa (različit `osm_id`) koja predstavljaju ISTI fizički objekat. Phase 9 dizajn ih namjerno tretira kao odvojene kategorije (eksplicitan zahtjev "trebaju mi sve vodene površine"), pa pipeline ispravno vraća oba -- ali korisniku na frontend-u to izgleda kao duplikat/greška. **Ovo je otvoreno pitanje o UX-u, ne backend bug** -- odluka o rješenju (geometrijsko spajanje kad se `river` i `water` geometrije preklapaju, potpuno izbacivanje jednog, ili vizuelno grupisanje bez dirania backend agregacije) je vraćena korisniku na odluku prije implementacije bilo kog rješenja (vidi razgovor).

2. **Neočekivano nizak `visible_fraction` (40-50%) za oba, na vrlo bliskoj (0.1-0.4 km) i naizgled potpuno otvorenoj rijeci.** Ovo NIJE prihvaćeno na oko (ni kao "sigurno bug" ni kao "sigurno tačno") jer:
   - Top-down 2D screenshot ne pokazuje elevaciju/teren -- "izgleda vidljivo" nije rigorozan dokaz o 3D line-of-sight-u, pogotovo ne na tako kratkoj distanci.
   - Ali obrnuto, postoji i konkretan tehnički razlog za sumnju: na 100-400 m distanci, `check_visibility()` (Phase 8) ima svega par desetina terenskih sample-ova (30 m spacing), pa je ugao vidljivosti EKSTREMNO osjetljiv na i najmanju terensku nepravilnost ili DEM šum -- Copernicus DEM GLO-30 je izveden iz TanDEM-X DSM-a (sekcija 25/26) i može nositi ostatke vegetacije/objekata čak i nakon "DEM" obrade, posebno duž riječnih obala gdje često ima drveća. Na tako kratkoj distanci, i par metara takvog šuma je dovoljno da promijeni visible/blocked odluku.

   **Nijedna od ove dvije teorije nije potvrđena bez pravih brojeva** -- zato je, umjesto nagađanja, dodata infrastruktura da se STVARNO provjeri: `AnalyzedAreaFeature.samples` (novo, opciono polje, isti princip kao `AnalyzedFeature.profile` -- populisano samo kad `?include_profile=true`) sada vraća PO SVAKOJ mini-viewshed sample tački: `latitude`/`longitude`, `distance_km`, `elevation_m` (DEM vrijednost na toj tački), `visible`, `target_angle_deg`, `max_terrain_angle_deg`. Ovo je identičan nivo detalja koji je već ranije (sekcija 27) korišten za ručnu `atan2` provjeru Kopaonik line-of-sight rezultata -- sad je dostupan i za area feature-e, ne samo tačkaste.

   Implementacija: `app.services.area_visibility.AreaSampleDiagnostic` (nova interna klasa), `AreaVisibilityResult.samples` (novo polje, `None` osim kad `collect_sample_details=True`), `evaluate_area_feature_visibility(..., collect_sample_details: bool = False)`, provučeno kroz `analyze.py` (`collect_sample_details=include_profile` -- isti flag koji već kontroliše profile za tačkaste feature-e, ne novi query parametar). Tri nova testa u `test_area_visibility.py` (samples None po defaultu, samples popunjen i tačan kad se zatraži, DEM-gap slučaj ostaje `None` rezultat kao i prije).

### Status testiranja

Kod je `python3 -m py_compile` provjeren (sintaksa). Nova `samples` dijagnostika ručno nije jos provjerena protiv stvarnog Sava slučaja -- to je sljedeći korak prije bilo kakvog zaključka o uzroku niskog `visible_fraction`-a.

**Napomena o promjeni radnog okruženja:** od ove tačke nadalje, `pip install` iz `device_bash` (bridge VM ka korisnikovoj mašini) RADI (ranije nepoznato -- prvi put testirano). To znači da je od sada mogao biti pokrenut PRAVI `pytest` (sa stvarnim `shapely`/`pydantic`/`rasterio` zavisnostima), ne samo `py_compile` sintaksna provjera, direktno od strane asistenta, bez čekanja na korisnika za taj korak. Overpass API (`overpass-api.de`) ostaje van dohvata (potvrđeno ranije, sekcija 27) -- ovo ne mijenja tu činjenicu, samo znači da su svi testovi koji NE zahtijevaju živi Overpass/DEM network poziv (tj. svi trenutni unit/integracioni testovi, koji mock-uju te servise) sada mogu biti samostalno pokrenuti i potvrđeni.

## 30. Rijeka/voda dedup -- geometrijsko spajanje (28.09.2026)

Korisnik je izabrao "geometrijsko spajanje" opciju za rješavanje dupliranih river/water rezultata (sekcija 29): kad se `river` i `water` geometrije PRESIJEKU, tretiraju se kao jedan fizički objekat.

- **`osm_areas.merge_overlapping_river_water_features()`** (nova funkcija) -- za svaku `river` liniju, pronalazi SVE `water` feature-e čija geometrija `.intersects()` tu liniju, i spaja ih u JEDAN `OSMAreaFeature` sa `geometry = GeometryCollection([river, *matched_waters])`. Zadržava ime/osm_id/kategoriju RIJEKE (informativnije od tipično bezimenog water poligona). Namjerno ograničeno na (river, water) parove -- park/national_park preklapanje nije prijavljeno kao problem. `OSMAreaFeature.geometry` tip proširen da uključi `GeometryCollection`.
- Pozvano u `analyze.py` odmah nakon Overpass fetch-a, PRIJE sector-intersect/sampling koraka -- `area_visibility.sample_points_for_geometry()` već rekurzivno sample-uje svaku komponentu GeometryCollection-a (nepromijenjeno, postojalo je i ranije za rijedak GeometryCollection edge case iz samog sector intersect-a), pa sam visibility algoritam NIJE dirat.
- **Empirijski provjereno PRIJE pisanja finalne implementacije** (asistent je direktno testirao preko `python3` + `shapely` u bridge VM-u, ne pretpostavka): `GeometryCollection([LineString, Polygon]).intersection(sector_polygon)` -- kad je linija PODSKUP poligona (potpuno pokrivena), rezultat kolabsira na sam Polygon (linija se gubi, ali to je bezopasno -- polygon grid sampling već pokriva to isto područje, šire). Kad linija IZLAZI izvan poligona (realniji slučaj -- `waterway=river` obično je duža od `natural=water` segmenta koji ga pokriva), rezultat je ispravno `GeometryCollection` sa LineString dijelovima IZVAN poligona + samim Polygon-om -- tačno ono što je pipeline-u potrebno.
- **6 novih testova** (`test_osm_areas.py`) sa sintetičkom geometrijom: bez preklapanja (ostaju odvojeni), spajanje jedne rijeke+vode, spajanje jedne rijeke sa VIŠE vodenih poligona, nepovezan water feature ostaje netaknut pored spojenog, park/national_park se NE dira, prazna lista.

### Status testiranja

**Pokrenuto od strane asistenta** (prvi put moguće u ovoj sesiji, vidi napomenu gore), u dva koraka: nakon dodavanja `samples` dijagnostike (sekcija 29) -- **151 passed, 0 failed** (148 prethodnih + 3 nova testa); nakon dodavanja merge funkcije (ova sekcija) -- **157 passed, 0 failed** (151 + 6 novih merge testova). Ovo POKRIVA sintetičku/mock geometriju (unit nivo) -- NE pokriva pravu Sava OSM geometriju iz Overpass-a (van dohvata odavde) niti pravi Kopaonik/Sava DEM slučaj u punom pipeline-u. Korisnička ručna Swagger provjera protiv STVARNE Sava lokacije je i dalje potreban sljedeći korak prije push-a -- vidi pitanje asistenta u razgovoru.

## 31. Uzrok niskog visible_fraction (Sava/Orašac) -- potvrđeno i ublaženo ugaonom tolerancijom (28.09.2026)

Korisnik je dao tačne koordinate (44.74396, 19.79281) i pokrenuo `/api/v1/analyze/preview?...&include_profile=true` na PRAVOJ Sava lokaciji. Rezultat je vraćen sa dva area feature-a: "Добрava" (river, 33% vidljivo) i "Сава" (river, 0% vidljivo, svih 5 sample-ova blokirano) -- BEZ duplikata "Vodena površina" (dedup fix iz sekcije 30 je potvrđen na pravim OSM podacima, radi ispravno).

**Asistent je nezavisno provjerio DEM na tačnim koordinatama** (offline, direktno iz `Copernicus_DSM_COG_10_N44_00_E019_00_DEM.tif` preko `rasterio`, bez mreže): DEM elevacija posmatrača je 76.25 m. Teren u tom pojasu (poplavna ravnica/nasip pored Save) je gotovo ravan, ALI varira 71.5-82.4 m na susjednim 30 m pikselima na svega 30-90 m od posmatrača.

**Analiza pravih `samples` podataka** (margina = `max_terrain_angle_deg - target_angle_deg`; pozitivna margina = blokirano po starom, strogom pravilu):

| Feature | sample distance | margina (°) |
|---|---|---|
| Добрava #2 | 207 m | 2.267 |
| Добрava #3 | 359 m | 1.507 |
| Сава #1 | 279 m | 0.671 |
| Сава #2 | 479 m | 0.096 |
| Сава #3 | 316 m | 1.668 |
| Сава #4 | 501 m | 1.223 |
| Сава #5 | 560 m | 1.068 |

**Zaključak (potvrđeno realnim brojevima, ne pretpostavka):** kod nije bio pogrešan -- `atan2`/poređenje su radili tačno po specifikaciji. Problem je bio strukturan: algoritam nije imao TOLERANCIJU za DEM vertikalnu nesigurnost, pa je i sitna, unutar-šuma razlika (npr. Сава #2, samo 0.096°) blokirala cilj isto strogo kao i znatno veća (Добрava #2, 2.267° -- ovo je verovatno stvaran, ako i mali, teren/nasip, ne čist šum).

**Implementirana izmjena** (korisnička odluka, ova sesija):
- `Settings.observer_eye_height_m`: 1.7 -> **1.85 m** (mala korekcija, sporedan efekat naspram tolerancije).
- Nova `Settings.dem_vertical_accuracy_m = 2.0` (sredina dokumentovanog 1-4 m opsega za Copernicus GLO-30, sekcija 26 -- NE pesimistički gornji kraj).
- Nova `visibility._angular_tolerance_deg(distance_m, vertical_accuracy_m) = atan(vertical_accuracy_m / distance_m)`, u stepenima -- namjerno SKALIRANO PO DISTANCI terenske tačke (ista vertikalna greška je ~3.8° na 30 m ali ~0.004° na 30 km -- tačno željeno ponašanje: popustljivije tik uz posmatrača gdje je algoritam najosjetljiviji, zanemarljivo na velikim distancama).
- `check_visibility()` sad poredi terensku tačku sa `target_angle_deg + tolerance_deg(te tačke)`, ne sa golim `target_angle_deg`. Tolerancija se namjerno NE primjenjuje na sam target ugao (pojednostavljenje za MVP).

**Očekivan efekat na realne brojeve iznad** (sa `dem_vertical_accuracy_m=2.0`, ne uzimajući u obzir malu promjenu eye height-a): tolerancija na 479 m je `atan(2/479)=0.239°` > margina 0.096° kod Сава #2 -> ta tačka postaje VISIBLE. Ostale margine (0.671-2.267°) premašuju čak i tolerantniju granicu izvedenu iz gornjeg kraja dokumentovane tačnosti (4 m), pa ostaju BLOCKED -- ovo je namjerno: tolerancija apsorbuje ČIST DEM šum, ne pretvara stvaran (makar i mali) teren/nasip u nevidljivu prepreku "od struje".

**Status testiranja:** `python3 -m py_compile` OK; puni `pytest` (pokrenut od strane asistenta, isti pristup kao sekcija 30) -- **159 passed, 0 failed** (157 prethodnih + 2 nova testa za toleranciju: jedan potvrđuje da mala margina ispod tolerancije ostaje VISIBLE, drugi da margina veća od tolerancije i dalje ostaje BLOCKED).

**ŽIVA POTVRDA na pravom Sava slučaju (korisnik je ponovo pozvao isti URL nakon izmjene):**

| Feature | prije | poslije |
|---|---|---|
| "Сава" | 0/5 vidljivo (0%) | **5/5 vidljivo (100%)** |
| "Добрava" | 1/3 vidljivo (33%) | **2/3 vidljivo (67%)**, jedan segment (207 m) ostaje realno blokiran |

Rezultat je BOLJI nego što je asistentova ručna procjena (gore u ovoj sekciji) predviđala, i uzrok te razlike je razumljiv i vrijedan zabilježiti: ručna procjena je (pogrešno) računala toleranciju koristeći distancu DO SAME sample tačke (npr. 359 m -> tolerancija 0.32°), dok kod ispravno računa toleranciju ZA SVAKU terensku tačku IZMEĐU posmatrača i cilja koristeći NJENU SOPSTVENU distancu od posmatrača -- a tačka koja određuje `max_terrain_angle_deg` je često mnogo bliže posmatraču (npr. ~60 m, ista DEM "grba" od ~78-79 m identifikovana ranije u ovoj sekciji) nego sama sample tačka, pa dobija mnogo veću toleranciju (atan(2/60)=1.91° naspram atan(2/359)=0.32°). Ovo NIJE bug u kodu -- kod je uvijek radio ono što je specificirano (tolerancija po terenskoj tački, ne po target tački); asistentova brza ručna procjena prije re-testa je bila pojednostavljena aproksimacija, ispravljena ovdje protiv stvarnog ponovljenog API poziva.

"Добрava" segment na 207 m ostaje blocked i nakon tolerancije -- ovo se tretira kao ISPRAVAN rezultat (djelimično vidljiva mala rijeka zbog stvarnog, makar i malog, terena/nasipa), ne kao preostali bug.

**Oba otvorena pitanja iz sekcije 29 (dupli river/water rezultati, nizak visible_fraction) su sada zatvorena i potvrđena na pravim OSM/DEM podacima.** Push četiri lokalna commit-a je odobren -- vidi "Sljedeći korak".

## 32. Phase 11 provjera + privremeni HTTPS tunnel za pravo testiranje na telefonu (28.09.2026)

**Phase 11 ("phone altitude diagnostics", brief sekcija 54) provjeren PRIJE pisanja koda -- nema novog posla.** CASE A-D logika iz brief-a (tačka 11) je već potpuno implementirana u Phase 7 (`location_quality.py`): DEM je uvijek autoritativan izvor za `selected_ground_elevation_m`, phone altitude ostaje dijagnostički podatak, bez obzira na `phone_altitude_accuracy_m` -- pokriveno sa 12 postojećih testova. `ElevationSource` Literal tip sadrži i `"dem_phone_fusion"`/`"dem_phone_disagreement"` (šema, sekcija 6), ali logika koja bi ih postavljala je namjerno neaktivna -- dokumentovano u `location_quality.py` docstring-u već od Phase 7, sa konkretnim tehničkim razlogom: browser/phone GPS altitude je tipično WGS84 elipsoidna visina, dok je Copernicus DEM EGM2008 orthometric height; razlika (geoid undulation) je na Balkanu ~40-45 m, pa bi naivna fuzija bez geoid korekcije unijela ogromnu sistematsku grešku bez načina da se empirijski provjeri bez pravog uređaja. Brief sam (tačka 12) eksplicitno dozvoljava ovaj ishod: "ako reliable vertical datum conversion nepotrebno komplikuje MVP, DEM ostaje authoritative source." Frontend (Phase 10) već prikuplja i prikazuje phone altitude/accuracy u debug panelu. Zaključak: Phase 11 je zadovoljen postojećim radom, ne treba novi kod.

**Stvarna praznina nije u kodu nego u verifikaciji:** ni Phase 10 (geolocation) ni planirani Phase 12 (compass/`DeviceOrientationEvent`) nisu testirani na PRAVOM telefonu, jer oba API-ja zahtijevaju secure context (HTTPS ili localhost) -- LAN IP pristup sa telefona ka desktop dev serveru ne radi (poznato ograničenje, zapisano već u Phase 10 commit poruci). Ovo je bilo planirano da se riješi tek u Phase 15 (deployment), ali to bi značilo da se Phase 12 piše i ostaje neverifikovan sve do kraja projekta -- korisnik je odlučio (vidi razgovor) da umjesto toga sad postavimo PRIVREMENI HTTPS tunnel, da se Phase 10/11 stvarno potvrde na telefonu i da se Phase 12 odmah testira uživo čim se napiše.

**Implementacija (omogućava tunnel testiranje, ne zamjenjuje Phase 15):**
- `backend/app/main.py`: CORS `allow_origin_regex` za `https://*.trycloudflare.com`, uslovljeno na `Settings.environment == "development"` (nikad aktivno u produkciji).
- `frontend/src/config.js`: `resolveBackendBaseUrl()` sad čita `?backend=<url>` query parametar prije fallback-a na hostname-based logiku -- rješava to što frontend, otvoren preko tunnel URL-a, ima `window.location.hostname` različit od "localhost", pa bi inače pao na placeholder Render URL. Bez perzistencije (namjerno) -- važi samo za tu posjetu.

**Alat: `cloudflared` "quick tunnel"** -- besplatan, bez naloga/prijave, nasumičan `https://xxxx.trycloudflare.com` subdomen po pokretanju. Odabran umjesto ngrok-a jer ngrok free tier traži registraciju i authtoken, cloudflared quick tunnel ne traži ništa. Mora se pokrenuti NA KORISNIKOVOJ MAŠINI (ne iz asistentovog `device_bash` bridge VM-a -- to je odvojena mreža/mašina i ne bi vidjela lokalne `localhost:8000`/`:5500` servise korisnikovog stvarnog desktopa), pa korisnik pokreće komande sam (isti princip kao i sve dosadašnje Swagger/browser provjere).

**Procedura (dokumentovana ovdje za ponovnu upotrebu -- ista dva tunnela trebaju i za Phase 12 test):**
1. Backend (`uvicorn app.main:app --reload`) i frontend (`python -m http.server 5500`) moraju već raditi kao i do sad.
2. U DVA nova terminala: `cloudflared tunnel --url http://localhost:8000` (backend) i `cloudflared tunnel --url http://localhost:5500` (frontend) -- svaki ispiše svoj `https://xxxx.trycloudflare.com` URL.
3. Na telefonu otvoriti FRONTEND tunnel URL sa `?backend=<BACKEND_TUNNEL_URL>` dodatim kao query parametar.
4. Testirati geolocation dugme -- ovo je prva prava provjera Phase 10/11 na stvarnom uređaju.

**Status testiranja:** `python3 -m py_compile`/`node --check` OK, puni `pytest` -- 159 passed, 0 failed (bez novih testova -- ovo je infrastruktura za testiranje, ne GIS logika). Stvarni tunnel/telefon test čeka korisnika (potrebna instalacija `cloudflared` na njegovoj mašini -- `winget install --id Cloudflare.cloudflared` na Windows-u, ili direktan download binarnog fajla).

## 33. Rezultati prvog pravog telefon testa -- UI bug fix + redizajn liste + izmenjeni defaulti (28.09.2026)

Prvi pravi test preko HTTPS tunela (sekcija 32) je otkrio jedan pravi bug i doveo do niza korisničkih odluka o dizajnu.

**Bug (nađen i popravljen prije bilo kojih dizajnerskih izmjena):** duga Overpass 504 greška se prikazivala DVA PUTA (u `resultsPanel` I u `#statusBanner`). `statusBanner` nije imao ni max-visinu ni dugme za zatvaranje, pa se razvukao preko `#actionBar` dugmadi i fizički blokirao klik (isti z-index, statusBanner kasnije u DOM-u -- pobjeđuje na klik). Dugme "Šta gledam?" je zapravo bilo ispravno ponovo omogućeno (finally blok) -- problem je bio isključivo u tome što je postalo nedostupno za klik. Popravka: analyze greške se sada prikazuju SAMO kroz `resultsPanel` (već ima `max-height`/`overflow-y:auto`); `statusBanner` dobija dugme za zatvaranje i sopstveni `max-height`/`overflow-y` kao trajnu zaštitu, bez obzira na dužinu buduće poruke.

**Korisničke odluke o rezultatima liste** (nakon što je korisnik vidio pravi izgled na telefonu):

1. **Default FOV 50°->30°, default radius 20 km->5 km** (`backend/app/core/config.py`, `frontend/src/config.js`) -- opsezi i njihovo obrazloženje iz sekcije 8 ostaju nepromijenjeni, mijenja se samo početna vrijednost slajdera.
2. **Jedna ravna lista, bez sekcija** ("Tačke" / "Rijeke i vode" heading-i uklonjeni) -- korisnik je ocijenio da odvojene sekcije nisu potrebne za jedan pogled u sektor. Lista se sad sortira: visible prvo, zatim partially_visible, zatim blocked (brief tačka 35), unutar iste grupe bliži prvo.
3. **Uklonjeno dupliranje informacije o vidljivosti** -- svaki red je ranije prikazivao I obojeni VIDLJIVO/DJELIMIČNO/ZAKLONJENO bedž I tekstualno "X% vidljivo" u podnaslovu -- ista informacija dva puta. Sada red pokazuje samo ime (podebljano) + bedž gore, i JEDNU riječ kategorije ispod (npr. "Reka", "Naselje") -- distance/bearing/procenat su uklonjeni iz liste (i dalje postoje u `analysis` objektu i debug panelu za onog kome trebaju).
4. **Neimenovani feature-i se ne prikazuju** -- korisnik je primijetio da se pored imenovane rijeke/reke i dalje pojavljuje bezimena "Vodena površina" koja je, po njegovoj procjeni, isti fizički objekat (dio Dunava) koji `merge_overlapping_river_water_features()` (sekcija 30) iz nekog razloga nije spojio sa imenovanom rijekom -- vjerovatno zato što se ta konkretna vodena poligon-sekcija geometrijski ne preklapa sa `waterway=river` linijom Dunava na tom mjestu (Dunav je veoma širok, `river` linija ne prati nužno svaku vodenu površinu duž toka). Umjesto da se merge logika širi da pokuša uhvatiti svaki ovakav slučaj, korisnik je odabrao jednostavnije rješenje na nivou prikaza: **feature bez imena se uopšte ne prikazuje** (`frontend/src/ui/resultsPanel.js`, `buildRows()` filtrira `row.name` prije renderovanja). Ovo je namjerno jednostavnije rješenje od proširivanja geometry merge-a -- eksplicitan kompromis: gubimo prikaz istinski bezimenih, izolovanih vodenih površina (rijetko korisno planinaru), ali dobijamo čistu listu bez zbunjujućih duplikata, bez dodatne geometrijske komplikacije.
5. **Ekavica, ne ijekavica** -- "Rijeka" -> "Reka", "DJELIMIČNO" -> "DELIMIČNO" (`AREA_CATEGORY_LABELS`, `VISIBILITY_BADGE_LABELS` u `resultsPanel.js`). Provjereno grep-om da nema drugih ijekavica riječi u korisnički vidljivom frontend tekstu (kod komentari ostaju ijekavica, kao i cijeli ostatak dokumentacije -- izmjena je namjerno ograničena na UI tekst koji korisnik stvarno vidi).

**Status testiranja:** `node --check` na svim izmijenjenim JS fajlovima OK, `python3 -m py_compile` OK, puni `pytest` -- 159 passed, 0 failed (bez izmjena GIS logike -- ovo je UI/config, ne backend algoritam). Novi izgled liste čeka korisnikovu vizuelnu potvrdu na telefonu prije push-a.

## 34. Drugi krug povratnih informacija sa telefona -- dedup po imenu, generički nazivi, transliteracija (28.09.2026)

Sljedeći test na telefonu (isti tunel, samo refresh stranice) je pokazao STARI izgled liste -- ijekavicu ("Rijeka", "DJELIMIČNO"), sekcijske naslove, dupli Dunav, distance/bearing/procenat -- iako je FOV/radius slajder ispravno pokazivao nove default vrijednosti (30°/5 km) iz iste izmjene. Ovo je jak signal keširanja (browser ES-modul keš i/ili Cloudflare edge keš statičkih `.js`/`.css` fajlova na `trycloudflare.com` domenu), NE da izmjene iz sekcije 33 nisu zapravo napisane na disk -- provjereno je da su fajlovi na disku ispravni prije nego što je bilo šta ponovo mijenjano. **Preporuka korisniku za sljedeći test: potpuno zaustaviti i ponovo pokrenuti OBA `cloudflared` tunela** (novi nasumični URL nema istoriju keša), umjesto oslanjanja na obično osvježavanje iste stranice.

Korisnik je u istoj poruci dao precizniju, opštiju verziju prethodnog zahtjeva (sekcija 33, tačka 3-4), sa tri konkretna nova zahtjeva:

1. **Spajanje duplikata PO IMENU, ne samo za Dunav.** "Ako je vidljivo jednom, ne prikazuj isti objekat 2 puta. Ovo se ne odnosi samo na Dunav nego na sve." Uzrok dupliranja (potvrđeno OSM uvidom): velike rijeke poput Dunava su u OSM-u često podijeljene u VIŠE odvojenih `way` segmenata koji dijele isti `name` tag -- ovo NIJE isti slučaj kao geometrijsko preklapanje river/water poligona iz sekcije 30 (`merge_overlapping_river_water_features()`, koje i dalje ostaje jer rješava drugi problem), nego dodatni, nezavisan izvor duplikata na nivou prikaza. Implementirano: nova funkcija `mergeDuplicateNames(rows)` u `resultsPanel.js`, grupiše redove po ključu `(ime, kategorija)` -- namjerno NE po imenu samom (isto ime u različitim kategorijama, npr. selo i rijeka, ostaju odvojeni redovi jer bi spajanje bilo pogrešno). Za svaku grupu duplikata bira se najbolja (najniža rank) vidljivost i najmanja distanca.
2. **Generički nazivi kategorije kao "ime" se ne prikazuju.** Korisnik je primijetio da se pojavljuje red sa imenom "Vodena površina" -- to nije stvaran OSM naziv nego doslovan tekst koji je neko unio u `name` tag kao generički opis ("to nije zvanični naziv i pravo ime nego generički naziv"). Filter je proširen sa "nema imena" (sekcija 33, tačka 4) na "nema imena ILI je ime identično prikazanoj kategoriji": `rows.filter((row) => row.name && row.name !== row.categoryLabel)`.
3. **Transliteracija ćirilice u latinicu.** "neka svi objekti budu na latinici a ne da mešaš ćirilicu i latinicu" -- OSM podaci za Srbiju često imaju `name` tag na ćirilici (npr. "Дунав", "Панчево"), dok je ostatak UI-ja (kategorije, dugmad, poruke) na latinici, pa mješavina u istoj listi izgleda nedosljedno. Dodat novi modul `frontend/src/utils/text.js` (`cyrillicToLatin()`) -- puna, deterministička 1:1 fonetska mapa (srpska ćirilica/latinica su u punoj korespondenciji, za razliku od npr. ruskog, pa nije potreban NLP/rječnik), uključujući digrafe (Љ→Lj, Њ→Nj, Џ→Dž). Primijenjeno na `feature.name` u `resultsPanel.js` (oba tipa reda) I u `resultsRenderer.js` (naslov mape popup-a) -- korisnički zahtjev je opšti ("svi objekti"), ne ograničen na listu rezultata, pa je dosljedno primijenjeno svuda gdje se `feature.name` prikazuje korisniku.

**Status testiranja:** `node --check` na sva tri izmijenjena/nova fajla (`resultsPanel.js`, `resultsRenderer.js`, `utils/text.js`) OK. Ručno testirana `cyrillicToLatin()` na stvarnim OSM imenima iz Kopaonik/Pančevo odgovora ("Дунав"->"Dunav", "Панчево"->"Pančevo", "Бутуч"->"Butuč", "Качарево"->"Kačarevo") -- ispravno. Puni `pytest` ponovo pokrenut nakon ovih izmjena (frontend-only, bez dodirivanja backend GIS logike) -- **159 passed, 0 failed**, potvrđuje da ništa u backend liniji vida/geometrije/OSM-a nije slučajno pogođeno. Ovaj drugi krug takođe čeka korisnikovu vizuelnu potvrdu na telefonu (nakon restarta tunela, vidi gore) prije push-a.

## Sljedeći korak

Dokument je odobren (sekcija 0). Implementacija napreduje faza po fazu -- napredak i odluke iz svake faze se dodaju u ovaj dokument. Backend (Phase 1-9) je potpuno implementiran, testiran i verifikovan. Frontend Phase 10 (rezultati UI + mobile geolocation, spojeno -- sekcija 28) je implementiran; prvi ručni test je otkrio dva otvorena pitanja (sekcija 29) -- OBA su sada riješena i POTVRĐENA na pravim podacima (sekcije 30-31): dupli river/water rezultati (geometrijsko spajanje, potvrđeno na pravoj Sava OSM geometriji -- nema više duplikata) i nizak visible_fraction (ugaona tolerancija izvedena iz DEM vertikalne tačnosti + eye height 1.7->1.85 m, potvrđeno živim re-testom -- "Сава" 0%->100%, "Добрava" 33%->67%). Pytest 159/159. Nakon toga, dva kruga UI povratnih informacija sa pravog telefon testa (sekcije 33-34): UI bug (statusBanner blokirao dugmad -- popravljeno), redizajn liste rezultata (ravna lista bez sekcija, bez dupliranja distance/bearing/procenta, ekavica, FOV/radius default 30°/5km), zatim dedup po imenu (ne samo Dunav), filter generičkih naziva, i transliteracija ćirilice u latinicu -- svi kod-nivo verifikovani (node --check, pytest 159/159), ČEKAJU korisnikovu vizuelnu potvrdu na telefonu (preporučeno: sa svježe restartovanim tunelima, zbog sumnje na keširanje -- sekcija 34) prije push-a. Nakon potvrde: Phase 12 (device orientation/compass), testirano preko iste tunel infrastrukture.

Ti commit-i su push-ovani i potvrđeni na GitHub-u. Phase 11 je provjeren i zatvoren bez novog koda (sekcija 32) -- CASE A-D logika je već bila potpuno gotova od Phase 7. Privremena HTTPS tunnel infrastruktura (sekcija 32) je postavljena i korišćena za prvi pravi telefon test -- geolokacija, sektor i kontrole rade ispravno na stvarnom uređaju. Test je otkrio jedan pravi UI bug (dugačka greška blokirala dugmad, popravljeno) i doveo do niza korisničkih odluka o izgledu rezultata (ravna lista bez sekcija, bez dupliranja vidljivosti, bez neimenovanih feature-a, ekavica, manji default FOV/radius -- sve u sekciji 33). Sljedeći korak: korisnik vizuelno potvrđuje novi izgled liste na telefonu; nakon potvrde slijedi push, pa Phase 12 (device orientation/compass) implementacija i uživo testiranje istom tunnel postavkom.