"""
Deljena HTTP/mirror-fallback logika za Overpass API pozive.

Zašto je ovo sada deljeno (za razliku od ranije namjerne duplikacije u
`osm.py`/`osm_areas.py` -- vidi njihove docstringove): tada je dupliranje
bilo opravdano jer je HTTP dio bio mali i identičan, a parsing suštinski
različit (node naspram way/relation geometrije). Sada dodajemo
multi-mirror fallback (Phase 15 nalaz, deployment na Render), pa bi se
mirror lista i retry-per-mirror logika inače identično duplirala na dva
mjesta -- to je dovoljno da opravda mali shared helper, dok parsing
odgovora ostaje odvojen u svom servisu, kako i treba.

KONTEKST NALAZA (28-29.09.2026, vidi docs/architecture-feasibility-review.md):
nakon deploya na Render, `overpass-api.de` je vraćao "All connection
attempts failed" -- ovo NIJE HTTP status greška (429/503/itd.), nego
greška na nivou TCP konekcije, dosljedna sa poznatim OSM community
izvještajima da `overpass-api.de` blokira čitave opsege IP adresa
deljenih cloud hosting provajdera (drugi zakupac istog provajdera je
ranije preopteretio server sa te iste deljene IP adrese). Ovo se
DOGAĐA SA LOKALNOG RAZVOJNOG OKRUŽENJA, gdje `overpass-api.de` radi
normalno preko kućne/mobilne mreže -- zato ostaje PRVI/podrazumevani
mirror (radi lokalni development bez izmene), a fallback lista postoji
za produkcioni (Render) slučaj.

AŽURIRANO (isti dan, nakon produkcionog testa): `overpass.osm.ch` je
PRVOBITNO dodat kao prvi fallback jer je brzo odgovarao, ali je naknadno
empirijski potvrđeno (upit protiv centra Züricha -- garantovano gusto
mapirana oblast) da taj mirror vraća PRAZAN `elements` niz za SVAKU
lokaciju, uvijek, sa HTTP 200 -- dakle "radi" (nikad ne baca grešku) ali
nikad ne vraća stvarne podatke. Ovo je OPASNIJE od obične nedostupnosti:
kod ovo tretira kao legitiman "nema rezultata" odgovor umjesto da pređe
na sljedeći mirror. UKLONJEN iz liste. `overpass.private.coffee` ostaje
(spor, ali potvrđeno vraća STVARNE podatke kad odgovori), a
`overpass-api.de` ostaje kao poslednji pokušaj (radi za lokalni razvoj
preko kućne mreže; na Renderu možda blokiran, ali besplatno je probati
kao zadnju opciju).

VAŽNO -- ponašanje kod trajnih (ne-tranzitornih) HTTP grešaka je
NAMERNO ostalo "abortuj odmah, ne probaj sledeći mirror": upit koji je
sintaksno loš (npr. 400) biće podjednako loš na svakom Overpass mirror-u
(svi govore isti Overpass QL), pa bi probanje ostalih mirror-a samo
trošilo vrijeme bez ikakve šanse za uspjeh. Fallback na sledeći mirror
se dešava SAMO za konekcijske greške i tranzitorne HTTP statuse
(429/502/503/504) -- baš onu vrstu greške koja je mirror-specifična, ne
upit-specifična. Ovo je pokriveno testovima u test_osm.py/test_osm_areas.py
(`..._does_not_retry_permanent_error`).
"""

from __future__ import annotations

import asyncio

import httpx

from app.core.config import Settings

# Kraći per-attempt timeout (bio 25s u staroj, single-mirror verziji) --
# sada probamo VIŠE mirror-a u istom zahtjevu, pa dugo čekanje na SVAKOM
# prije prelaska na sljedeći poništava svrhu fallback-a. Cilj: brzo
# saznati da je mirror spor/nedostupan i preći dalje, ne trošiti budžet
# vremena bitnog za LinkedIn demo (brief tačka 50) na jedan spor server.
_PER_ATTEMPT_TIMEOUT_S = 12.0

_TRANSIENT_STATUS_CODES = {429, 502, 503, 504}

# `Settings.overpass_api_url` ostaje KONFIGURABILAN prvi/preferirani
# mirror (npr. za lokalni razvoj gdje overpass-api.de radi normalno preko
# kućne mreže, ili za ručno postavljanje drugog mirror-a preko env
# varijable bez izmjene koda). Ako je već u listi ispod, ne duplira se.
_FALLBACK_MIRRORS: list[str] = [
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


class OverpassHTTPError(RuntimeError):
    """Podignuto kad SVI mirror-i iscrpe svoje pokušaje bez uspjeha, ili
    odmah kad neki mirror vrati trajnu (ne-tranzitornu) grešku."""


def _build_mirror_list(settings: Settings) -> list[str]:
    mirrors = [settings.overpass_api_url]
    for url in _FALLBACK_MIRRORS:
        if url not in mirrors:
            mirrors.append(url)
    return mirrors


async def fetch_overpass_json(settings: Settings, query: str, user_agent: str) -> dict:
    """Proba svaki mirror iz `_build_mirror_list` redom. Unutar svakog
    mirror-a radi do `settings.overpass_max_retries` dodatnih pokušaja
    SAMO za tranzitorne greške (mrežni/konekcijski problem ili 429/502/
    503/504) -- vidi modul docstring za obrazloženje zašto se trajne
    greške NE prosleđuju na sljedeći mirror. Diže `OverpassHTTPError`
    čim naiđe na trajnu grešku, ili kad SVI mirror-i iscrpe pokušaje.
    """
    max_attempts_per_mirror = settings.overpass_max_retries + 1
    last_error: OverpassHTTPError | None = None

    for mirror_url in _build_mirror_list(settings):
        for attempt in range(1, max_attempts_per_mirror + 1):
            try:
                async with httpx.AsyncClient(timeout=_PER_ATTEMPT_TIMEOUT_S) as client:
                    response = await client.post(
                        mirror_url,
                        data={"data": query},
                        headers={"User-Agent": user_agent},
                    )
            except httpx.HTTPError as exc:
                last_error = OverpassHTTPError(f"{mirror_url} nedostupan: {exc}")
            else:
                if response.status_code == 200:
                    return response.json()

                if response.status_code not in _TRANSIENT_STATUS_CODES:
                    # Trajna greška -- ne vrijedi ni retry ni sljedeći
                    # mirror (isti upit, isti rezultat svuda).
                    raise OverpassHTTPError(
                        f"{mirror_url} vratio {response.status_code}: {response.text[:300]}"
                    )

                last_error = OverpassHTTPError(
                    f"{mirror_url} vratio {response.status_code}: {response.text[:300]}"
                )

            if attempt < max_attempts_per_mirror:
                await asyncio.sleep(settings.overpass_retry_backoff_s)
        # Mirror iscrpio sve pokušaje (samo za tranzitorne/konekcijske
        # greške) -- probaj sljedeći mirror iz liste.

    assert last_error is not None  # mirrors lista nikad nije prazna
    raise last_error
