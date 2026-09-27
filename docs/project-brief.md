# PROJECT BRIEF — GIS LANDSCAPE IDENTIFICATION MVP

> Ovo je originalni brief projekta (arhivirana kopija, septembar 2026), kako je definisan prije Architecture & Feasibility Review-a. Vidi `architecture-feasibility-review.md` u istom folderu za usvojenu arhitekturu i odluke koje preciziraju ili blago odstupaju od ovog originalnog teksta (npr. earth curvature van MVP-a, bez phone/DEM elevation fusion-a u MVP-u).

Želim da zajedno napravimo mali, ali profesionalno izveden GIS MVP koji ću javno objaviti na GitHubu i predstaviti na LinkedInu kao portfolio projekat u cilju demonstracije svojih GIS, Esri, Python, web-development i AI vještina.

**VAŽNO:** Ovo nije zamišljeno kao production-ready komercijalna aplikacija. Primarni cilj je napraviti funkcionalan, tehnički smislen, vizuelno atraktivan, lako demonstrabilan, dobro dokumentovan GIS portfolio MVP. Scope mora ostati dovoljno mali da projekat može biti završen.

## 1. Osnovna ideja

Aplikacija je prvenstveno namijenjena planinarima, turistima i ljudima koji se nalaze na otvorenom. Osnovno pitanje koje aplikacija treba da riješi je: **"What am I looking at?"**

Korisnik se nalazi na planini ili vidikovcu, pogleda prema horizontu i zapita se "Koja je ono planina?" ili "Šta se nalazi u tom pravcu?". Aplikacija je browser-based i mobile-first (bez native Android/iOS aplikacije).

## 2. Glavni user flow

Korisnik otvori URL na telefonu → dozvoli pristup lokaciji → aplikacija dobije poziciju → pokuša dobiti heading telefona → na ArcGIS karti se prikaže korisnik i viewing sector → korisnik podesi heading/FOV/radius → klikne "What am I looking at?". Backend pronađe geografske objekte u sektoru, izračuna distance/bearing, koristi DEM za elevaciju, radi terrain line-of-sight analizu, određuje vidljivost, vraća deterministički GIS rezultat koji OpenAI pretvara u kratak prirodan opis.

## 3. Portfolio cilj

Demonstracija: GIS-a, Esri ekosistema (ArcGIS Online, ArcGIS Maps SDK for JavaScript kao stvaran, vidljiv dio projekta — ne samo pomenut u README-u), web GIS-a, geolocation-a, koordinatnih sistema, geodesic calculations, bearing calculations, DEM/elevation podataka, terrain profiling, line-of-sight/visibility analize, OpenStreetMap podataka, Python-a, FastAPI-ja, REST API dizajna, frontend developmenta, browser/mobile senzora, Git/GitHub-a, API integracija, OpenAI API-ja, data quality/uncertainty handling-a.

## 4. Alati i troškovi

Već postoji: ArcGIS Online licenca, PyCharm, GitHub, OpenAI API pristup. Dodatni troškovi treba da budu minimalni ili nula — preferiraju se open-source biblioteke, besplatni dataseti/API-ji, free-tier hosting, postojeće mogućnosti ArcGIS Online licence. Bilo koji ArcGIS servis koji troši credits mora biti jasno označen prije implementacije.

## 5. Preferirani technology stack

**Frontend:** ArcGIS Maps SDK for JavaScript, HTML/CSS/JavaScript ili React + Vite ako postoji opravdanje.
**GIS/Web infrastruktura:** ArcGIS Online, ArcGIS Web Map ako je smislen, GraphicsLayer, ArcGIS geometry classes.
**Backend:** Python 3.x, FastAPI, Pydantic. GIS biblioteke po potrebi: PyProj, Shapely, Rasterio, rioxarray, NumPy. HTTP: httpx/requests.
**OSM:** OpenStreetMap preko Overpass API.
**Elevation:** Copernicus DEM GLO-30 (preferirano).
**AI:** OpenAI API.
**Version control:** GitHub.

## 6. Ključni princip

**GEOSPATIAL ANALYSIS FIRST. AI SECOND.** LOCATION + HEADING + OSM + DEM + GEOMETRY + LINE OF SIGHT → STRUCTURED GIS RESULT → OPENAI → NATURAL LANGUAGE. OpenAI ne smije odlučivati koji objekat postoji, gdje se nalazi, koliko je udaljen, koji mu je bearing/elevation, da li je vidljiv — sve to određuje GIS engine. AI samo objašnjava rezultat.

## 7. Geolocation i location quality

Koristi browser Geolocation API: latitude, longitude, accuracy, altitude (opciono), altitudeAccuracy (opciono), heading ako je dostupan. Altitude nije obavezan — ako je `null`, aplikacija mora normalno raditi. Horizontalna GPS greška (`coords.accuracy`) prati se i koristi za jednostavan, transparentan quality model (HIGH/MEDIUM/LOW), sa pragovima koji se prvo predlažu i obrazlažu, ne hardcoduju proizvoljno.

## 8. Observer elevation

DEM je primarni izvor visine (`terrain_elevation = DEM(lat, lon)`), `observer_elevation = terrain_elevation + observer_eye_height` (default 1.7 m, konfigurabilno u backendu). Phone altitude je sekundaran diagnostic signal — logika po slučajevima (altitude null / altitude bez accuracy / loša accuracy / dobra accuracy) definisana je u brifu; vertical datum problem (browser altitude vs. DEM vertical reference) mora biti istražen i dokumentovan prije bilo kakve fuzije; ako pouzdana transformacija nepotrebno komplikuje MVP, DEM ostaje autoritativan izvor, a phone altitude ostaje dijagnostički signal (ovo je i usvojena odluka — vidi architecture review).

## 9. Elevation fusion

Ne koristiti automatski prost prosjek phone i DEM altitude. Ako se fusion ikad implementira, koristiti weighted pristup sa DEM-om kao dominantnim faktorom, tek nakon analize i usklađivanja vertikalnog datuma — ne uzimati konkretne težine kao konačne bez obrazloženja. Ako nema dovoljno informacija da se opravda fusion: koristiti DEM.

## 10. Location quality model

Backend vraća dijagnostičke informacije: `horizontal_accuracy_m`, `phone_altitude_m`, `phone_altitude_accuracy_m`, `dem_elevation_m`, `selected_ground_elevation_m`, `elevation_source` (`dem` / `dem_phone_fusion` / `dem_phone_disagreement`), `confidence`. Ako se DEM i kvalitetan phone altitude značajno ne slažu, ne kombinovati nasilno — koristiti DEM i postaviti diagnostic flag. UI ne treba biti zatrpan ovim — može postojati mali expandable debug panel (može biti Phase 2 ako komplikuje MVP), ali backend mora biti dizajniran da ove informacije može vratiti.

## 11. Device orientation / compass

Istražiti browser podršku i permission flow za Android Chrome i iOS Safari (`DeviceOrientationEvent`, permissions, secure context/HTTPS, razlike između browsera, compass heading, sensor instability). Mora postojati fallback: AUTO MODE (koristi kompas) i MANUAL MODE (korisnik ručno podešava heading) — manual mode je **obavezan**, aplikacija ne smije zavisiti od toga da compass radi. Heading sa telefona može biti noisy — jednostavno smoothing/filtering rješenje (moving average ili exponential smoothing) implementirati samo ako testiranje pokaže potrebu, bez premature complexity.

## 12. Viewing sector, FOV, radius

Na osnovu lat/lon/heading/FOV/radius napraviti geometrijski viewing sector, vidljiv na ArcGIS karti kao poluprovidna geometrija. Korisnik podešava horizontalni FOV (predložiti razumne granice, npr. okvirno 20°–90°, default oko 45–50°) i maksimalnu udaljenost/radius (predložiti razumne opcije i default nakon analize, sa ciljem da se smanji OSM query/DEM sampling/ubrza line-of-sight).

## 13. OSM podaci

MVP počinje sa `natural=peak` preko Overpass API-ja (OSM ID, name, lat/lon, `ele` ako postoji, relevantni tagovi). Kasnije (Phase 2/Future) mogu se dodati `natural=volcano`, `natural=water`, `place=village/town`, `tourism=viewpoint`, `historic=*`, `amenity=shelter` — ne u Version 0.1. OSM licenca/attribution zahtjevi moraju biti poštovani u aplikaciji i README-u.

## 14. Candidate filtering, distance, bearing

Pipeline: OSM peaks → distance filter → bearing calculation → FOV/sector filter → candidate peaks → DEM/line-of-sight. Koristiti geodesic (ne naivnu Euclidean) distance i bearing proračune, testirane uključujući heading wrap-around slučajeve (359°/0°/1°).

## 15. DEM

Koristiti DEM (ne DSM), primarni kandidat Copernicus DEM GLO-30. Prije implementacije istražiti dostupnost, licencu, najjednostavniji pristup, potrebu za download-om tile-ova, postojanje odgovarajućeg servisa, performanse, eventualne ArcGIS opcije i credit cost. Ne birati automatski najkomplikovaniji način. Jasno razlikovati horizontalnu prostornu rezoluciju (30 m) od vertikalne tačnosti u dokumentaciji — "30 m DEM" ≠ "±30 m elevation error". Horizontalna GPS greška korisnika kao limitation (pomjeranje DEM sampling tačke na strmom terenu).

## 16. Target elevation

Koristiti OSM `ele` ako postoji i djeluje validno, inače DEM elevation na target koordinati; sačuvati `elevation_source`. Ako postoji velika razlika između OSM `ele` i DEM elevation, ne pretpostavljati automatski koji je ispravan — zabilježiti discrepancy, predložiti jednostavno pravilo prioriteta za MVP.

## 17. Line-of-sight algoritam

Ne raditi kompletan raster viewshed — za svaki candidate peak raditi individualni observer→target line-of-sight: geodesic linija, sampling tačaka duž nje, DEM elevation po tački, terrain elevation profile, elevation angle proračun (`atan2(terrain_elevation_i - observer_elevation, distance_i)`), poređenje sa target angle-om; ako bilo koja terenska tačka ima veći elevation angle od target angle-a, target je blocked, inače visible. Sampling interval mora imati smisla u odnosu na DEM rezoluciju (~30 m), uz eksplicitan tradeoff preciznost/brzina. Earth curvature i atmospheric refraction ne moraju biti u prvom prototipu, ali dizajn treba omogućiti kasnije dodavanje — procijeniti da li je potrebno s obzirom na izabrani max radius (usvojena odluka: van MVP-a jer je scope Srbija, vidi architecture review).

## 18. Elevation profile, GIS engine output, AI layer

Visibility service treba moći vratiti terrain profile (distance/elevation parovi) — UI graf je poželjan za portfolio ali može biti Phase 2. Backend vraća jasan strukturiran JSON (observer diagnostics, visible_features, blocked_features — konkretan predložen oblik dat u brifu, poboljšan Pydantic model po potrebi). OpenAI se poziva TEK nakon GIS analize, dobija samo strukturirani rezultat, sa sistemskim promptom koji zabranjuje izmišljanje objekata/elevacije/distance/bearing-a, traži jasno razlikovanje visible/blocked, kratak i prirodan odgovor, i poštovanje slučaja "nema dovoljno identifikovanih objekata". AI layer nije core sistema — ako OpenAI ne radi, GIS aplikacija mora nastaviti da radi.

## 19. Frontend, results panel, ArcGIS SDK/Online

Frontend: mobile-first, responsive, čist, jednostavan, dovoljno atraktivan za LinkedIn demo — mapa, user marker, viewing sector, kontrole (heading/FOV/radius), dugme "What am I looking at?", results panel (za svaki rezultat: ime, distance, elevation, bearing, visible/blocked status — visible vizuelno važniji od blocked). Demonstrirati stvarnu upotrebu ArcGIS Maps SDK for JavaScript (Map/WebMap, MapView, GraphicsLayer, Point, Polygon, custom viewing sector, symbols, popups, mobile geolocation integracija) — custom sector logika mora biti vidljiva, ne sakrivena iza gotovih widgeta. ArcGIS Online treba biti stvaran dio sistema (Web Map, basemap, eventualni hosted layer, application item, sharing) — za svaku komponentu navesti zašto se koristi, da li troši credits, koliko približno, i da li postoji besplatna alternativa.

## 20. Desktop development mode, backend/frontend struktura, security

Aplikacija se prvenstveno razvija na računaru — mora imati manual/development mode (klik na mapu postavlja observer, heading/FOV/radius ručno). Backend organizovan u module (ne jedan fajl) — predložena struktura: `app/main.py`, `api/routes/`, `models/`, `services/` (geometry, osm, elevation, location_quality, visibility, ai), `core/config.py`, `tests/`. Frontend organizovan sa razdvojenom logikom (`components/services/map/utils` ili slično). OpenAI API key nikada u frontend kodu — secrets u backend environment varijablama (`.env`, `.env.example`, `.env` u `.gitignore`).

## 21. Error handling, privacy, performance

Aplikacija mora normalno reagovati na: odbijen location permission, nedostupan geolocation, loš GPS accuracy, `null` phone altitude/altitudeAccuracy, nedostupan/odbijen compass, nedostupan Overpass/DEM/OpenAI, nema peakova u sektoru. Manual mode mora omogućiti testiranje i kada geolocation/compass ne rade. Bez user accounts, bez baze sa istorijom lokacija — lokacija se koristi samo za trenutnu analizu (jasno navedeno u README-u). Bez premature optimizacije; ako ima mnogo kandidata, analizirati npr. top 10–20 po jednostavnom ranking-u (angular proximity, distance, elevation, prominence ako dostupno).

## 22. Testovi, test lokacije, validacija

Obavezni unit testovi za GIS matematiku: distance, bearing, angular difference, FOV inclusion, sector edge cases, heading wrap-around (posebno 359°+1°), line-of-sight. Predložiti nekoliko test lokacija (najmanje jedna u Srbiji/Balkanu — usvojena odluka: sve u Srbiji, vidi architecture review) sa dobrim DEM pokrićem, više OSM peak objekata, jasnim terrain relief-om, kombinacijom visible/blocked vrhova, zapisanih kao deterministic test scenariji. Predložiti metode validacije line-of-sight engine-a (elevation profile inspection, poznati terenski testovi, poređenje sa drugim GIS visibility/viewshed alatom ili Esri servisima) — cilj je tehnički odbranjiv MVP, ne scientific-grade visibility engine.

## 23. Deployment, GitHub, LinkedIn demo

HTTPS obavezan (Geolocation/Device Orientation permissions). Predložiti trenutne (provjerene, ne zastarjele) skoro-besplatne opcije: frontend (GitHub Pages/Vercel/Netlify), backend (Render/Railway/druga opcija). GitHub repo mora izgledati profesionalno — README sa: project name, problem, demo, how it works, architecture (Mermaid diagram), tech stack, Esri/ArcGIS integracija, data sources, elevation/location quality/line-of-sight metodologija, AI role, API, local setup, env vars, testing, limitations, privacy, attribution, future improvements. Projekat dizajniran da se objasni u 20–40 sekundnom video/GIF demou za LinkedIn: otvaranje mape, postavljanje/učitavanje lokacije, okretanje sektora, promjena FOV-a, klik na "What am I looking at?", prikaz peakova i visible/blocked statusa, AI opis.

## 24. Šta NE raditi u MVP-u

Native Android/iOS app, AR camera overlay, camera image recognition/computer vision, offline maps/navigation, route planning, user accounts/authentication, social features, persistent user location database, complex PostGIS infrastruktura, full raster viewshed, global optimized DEM infrastruktura, 3D terrain engine, desetine OSM kategorija, machine learning model, komplikovan sensor fusion, production-scale caching, microservices. Ideje za ove stavke idu u README "Future Improvements", ne implementiraju se.

## 25. Implementacioni redoslijed (16 faza)

Project setup + ArcGIS mapa → Manual observer → Heading + FOV + viewing sector → OSM `natural=peak` integracija → Distance + bearing + candidate filtering → DEM integracija → Observer elevation + location quality arhitektura → Line-of-sight engine → Visible/blocked UI → Mobile geolocation → Phone altitude diagnostics → Device orientation/compass → OpenAI explanation → Testing → Deployment → README + architecture diagram + LinkedIn demo. Nakon svake faze aplikacija mora ostati pokretljiva i testabilna.

## 26. Definition of Done

MVP je završen kada je moguće: otvoriti javni HTTPS URL na telefonu, dozvoliti lokaciju, vidjeti poziciju na ArcGIS mapi, koristiti compass ili manual heading, vidjeti viewing sector, podesiti FOV i radius, kliknuti "What am I looking at?", dobiti OSM peak candidates sa distance/bearing, imati DEM-based terrain analizu i visible/blocked klasifikaciju, dobiti kratak AI opis, otvoriti GitHub repo sa kvalitetnim README-em, pokazati projekat u kratkom LinkedIn videu.
