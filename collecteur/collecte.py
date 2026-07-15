#!/usr/bin/env python3
"""Collecteur de la veille mondiale d'offres d'emploi de pilote.

Interroge des sources gratuites (flux RSS Google News dans toutes les grandes
langues + sites aéronautiques spécialisés), filtre les résultats pertinents,
traduit les titres en français, et alimente la base append-only
``data/annonces.json`` : aucune annonce n'est jamais supprimée, seules les
nouvelles sont ajoutées.

Usage : python collecteur/collecte.py
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "data" / "annonces.json"

ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; veille-emploi-pilote-perso/1.0)"}
DELAI_ENTRE_REQUETES = 1.0  # secondes — rester respectueux des serveurs

REGIONS = [
    "Europe",
    "Amérique du Nord",
    "Amérique du Sud",
    "Asie",
    "Moyen-Orient",
    "Océanie",
    "Afrique",
    "Monde",
]


def url_google_news(requete: str, hl: str, gl: str, ceid: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(requete)
        + f"&hl={hl}&gl={gl}&ceid={ceid}"
    )


# (nom, url, langue, région par défaut)
SOURCES = [
    (
        "SNPI (France)",
        "https://snpi.aero/offres-emploi/feed/",
        "fr",
        "Europe",
    ),
    (
        "Google News France",
        url_google_news(
            'recrutement pilote avion OR copilote OR "instructeur avion"',
            "fr", "FR", "FR:fr",
        ),
        "fr",
        "Europe",
    ),
    (
        "Google News États-Unis",
        url_google_news('"pilot jobs" OR "hiring pilots" OR "pilot recruitment" airline', "en-US", "US", "US:en"),
        "en",
        "Amérique du Nord",
    ),
    (
        "Google News Royaume-Uni",
        url_google_news('airline pilot recruitment OR "first officer" vacancy OR "flight instructor" job', "en-GB", "GB", "GB:en"),
        "en",
        "Europe",
    ),
    (
        "Google News Inde",
        url_google_news("pilot recruitment airline hiring", "en-IN", "IN", "IN:en"),
        "en",
        "Asie",
    ),
    (
        "Google News Australie",
        url_google_news("pilot jobs airline recruitment", "en-AU", "AU", "AU:en"),
        "en",
        "Océanie",
    ),
    (
        "Google News Afrique",
        url_google_news("pilot vacancy OR pilot recruitment airline africa", "en-ZA", "ZA", "ZA:en"),
        "en",
        "Afrique",
    ),
    (
        "Google News Amérique latine",
        url_google_news("empleo piloto aviación OR contratación pilotos aerolínea", "es-419", "AR", "AR:es-419"),
        "es",
        "Amérique du Sud",
    ),
    (
        "Google News Brésil",
        url_google_news("vaga piloto aviação OR contratação pilotos companhia aérea", "pt-BR", "BR", "BR:pt-419"),
        "pt",
        "Amérique du Sud",
    ),
    (
        "Google News Moyen-Orient",
        url_google_news("وظائف طيارين OR توظيف طيار شركة طيران", "ar", "AE", "AE:ar"),
        "ar",
        "Moyen-Orient",
    ),
    (
        "Google News Chine",
        url_google_news("飞行员 招聘 航空公司", "zh-CN", "CN", "CN:zh-Hans"),
        "zh",
        "Asie",
    ),
    (
        "Google News Japon",
        url_google_news("パイロット 採用 航空会社", "ja", "JP", "JP:ja"),
        "ja",
        "Asie",
    ),
    (
        "Google News Russie",
        url_google_news("вакансия пилот авиакомпания", "ru", "RU", "RU:ru"),
        "ru",
        "Europe",
    ),
    (
        "Google News Allemagne",
        url_google_news("Pilot Stellenangebot Airline OR Fluglehrer gesucht", "de", "DE", "DE:de"),
        "de",
        "Europe",
    ),
]

# --- Filtre de pertinence -----------------------------------------------
# Une annonce est retenue si son titre contient un mot "pilote" ET un mot
# "recrutement" (dans n'importe quelle langue couverte).

MOTS_PILOTE = re.compile(
    r"pilot|pilote|piloto|copilot|copilote|first officer|flight instructor"
    r"|instructeur|cadet|commandant de bord|fluglehrer"
    r"|飞行员|机长|パイロット|操縦士|طيار|пилот|лётчик|летчик",
    re.IGNORECASE,
)
MOTS_RECRUTEMENT = re.compile(
    r"job|hiring|hire|vacanc|recruit|recrut|embauche|carri[eè]re|career"
    r"|empleo|contrataci|vaga|contrata|stellen|gesucht|emploi|poste|offre"
    r"|apply|candidat|programme? cadet|cadet program|recherche"
    r"|招聘|招募|採用|募集|توظيف|وظائف|وظيفة|تعيين|вакансия|набор|требу",
    re.IGNORECASE,
)

# Affinage de la région : pays/villes repérés dans le titre.
INDICES_REGION = {
    "Moyen-Orient": [
        "emirates", "dubai", "dubaï", "qatar", "doha", "saudi", "arabie",
        "riyad", "riyadh", "abu dhabi", "etihad", "oman", "bahrain", "bahreïn",
        "kuwait", "koweït", "jordan", "jordanie", "liban", "lebanon", "israel", "israël",
        "الإمارات", "السعودية", "قطر", "دبي",
    ],
    "Asie": [
        "china", "chine", "hong kong", "japan", "japon", "india", "inde",
        "singapore", "singapour", "vietnam", "thailand", "thaïlande",
        "indonesia", "indonésie", "malaysia", "malaisie", "philippines",
        "korea", "corée", "taiwan", "taïwan", "cathay", "中国", "日本", "香港",
    ],
    "Océanie": ["australia", "australie", "new zealand", "nouvelle-zélande", "qantas", "fiji", "fidji"],
    "Afrique": [
        "africa", "afrique", "nigeria", "kenya", "ethiopia", "éthiopie",
        "south african", "maroc", "morocco", "algérie", "algeria", "tunisie",
        "tunisia", "egypt", "égypte", "sénégal", "senegal", "congo", "ghana",
    ],
    "Amérique du Nord": [
        "united states", "états-unis", "usa", "canada", "mexico", "mexique",
        "american airlines", "delta", "united airlines", "air canada", "westjet",
    ],
    "Amérique du Sud": [
        "brazil", "brésil", "brasil", "argentina", "argentine", "chile", "chili",
        "colombia", "colombie", "peru", "pérou", "latam", "azul", "gol ",
    ],
    "Europe": [
        "france", "germany", "allemagne", "spain", "espagne", "italy", "italie",
        "united kingdom", "royaume-uni", "ireland", "irlande", "portugal",
        "netherlands", "pays-bas", "belgium", "belgique", "suisse", "switzerland",
        "poland", "pologne", "ryanair", "easyjet", "lufthansa", "air france",
        "wizz", "vueling", "klm", "россия", "russie", "russia",
    ],
}


def normaliser_titre(titre: str) -> str:
    """Clé de dédoublonnage : titre en minuscules sans accents ni ponctuation."""
    titre = unicodedata.normalize("NFKD", titre)
    titre = "".join(c for c in titre if not unicodedata.combining(c))
    titre = re.sub(r"[^\w\s]", " ", titre.lower())
    return re.sub(r"\s+", " ", titre).strip()


def telecharger(url: str) -> bytes:
    requete = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return reponse.read()


def nettoyer_html(texte: str) -> str:
    texte = re.sub(r"<[^>]+>", " ", texte or "")
    texte = html.unescape(texte)
    return re.sub(r"\s+", " ", texte).strip()


def lire_flux_rss(contenu: bytes) -> list[dict]:
    """Extrait les items d'un flux RSS (titre, lien, date, description)."""
    racine = ET.fromstring(contenu)
    items = []
    for item in racine.findall(".//item"):
        titre = nettoyer_html(item.findtext("title") or "")
        lien = (item.findtext("link") or "").strip()
        if not titre or not lien:
            continue
        date_pub = ""
        brut = item.findtext("pubDate") or ""
        if brut:
            try:
                date_pub = parsedate_to_datetime(brut).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                date_pub = brut
        source_media = item.findtext("source") or ""
        items.append(
            {
                "titre": titre,
                "lien": lien,
                "date_publication": date_pub,
                "extrait": nettoyer_html(item.findtext("description") or "")[:400],
                "media": nettoyer_html(source_media),
            }
        )
    return items


def deviner_region(texte: str, region_defaut: str) -> str:
    texte_bas = texte.lower()
    for region, indices in INDICES_REGION.items():
        if any(indice in texte_bas for indice in indices):
            return region
    return region_defaut


def est_pertinent(titre: str, extrait: str) -> bool:
    champ = f"{titre} {extrait}"
    return bool(MOTS_PILOTE.search(champ)) and bool(MOTS_RECRUTEMENT.search(champ))


def traduire_fr(texte: str) -> str:
    """Traduction gratuite vers le français ; renvoie le texte original en cas d'échec."""
    try:
        from deep_translator import GoogleTranslator

        traduit = GoogleTranslator(source="auto", target="fr").translate(texte[:4500])
        return traduit or texte
    except Exception as erreur:  # noqa: BLE001 — la traduction ne doit jamais bloquer la collecte
        print(f"    (traduction impossible : {erreur})", file=sys.stderr)
        return texte


def charger_base() -> dict:
    if FICHIER_DONNEES.exists():
        return json.loads(FICHIER_DONNEES.read_text(encoding="utf-8"))
    return {"annonces": [], "derniere_collecte": None}


def sauvegarder_base(base: dict) -> None:
    FICHIER_DONNEES.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_DONNEES.write_text(
        json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def collecter() -> None:
    base = charger_base()
    ids_connus = {annonce["id"] for annonce in base["annonces"]}
    titres_connus = {
        normaliser_titre(annonce.get("titre_original") or annonce.get("titre_fr", ""))
        for annonce in base["annonces"]
    }
    maintenant = datetime.now(timezone.utc).isoformat()

    nouvelles = []
    for nom_source, url, langue, region_defaut in SOURCES:
        print(f"Source : {nom_source}")
        try:
            items = lire_flux_rss(telecharger(url))
        except Exception as erreur:  # noqa: BLE001 — une source en panne ne bloque pas les autres
            print(f"  ÉCHEC ({erreur})", file=sys.stderr)
            continue

        retenues = 0
        for item in items:
            if not est_pertinent(item["titre"], item["extrait"]):
                continue
            identifiant = hashlib.sha1(item["lien"].encode("utf-8")).hexdigest()[:16]
            cle_titre = normaliser_titre(item["titre"])
            if identifiant in ids_connus or cle_titre in titres_connus:
                continue

            titre_fr = item["titre"] if langue == "fr" else traduire_fr(item["titre"])
            annonce = {
                "id": identifiant,
                "titre_original": item["titre"],
                "titre_fr": titre_fr,
                "lien": item["lien"],
                "source": nom_source if not item["media"] else f"{item['media']} (via {nom_source})",
                "langue": langue,
                "region": deviner_region(f"{item['titre']} {item['extrait']}", region_defaut),
                "date_publication": item["date_publication"],
                "extrait": item["extrait"],
                "premiere_collecte": maintenant,
            }
            nouvelles.append(annonce)
            ids_connus.add(identifiant)
            titres_connus.add(cle_titre)
            retenues += 1
        print(f"  {len(items)} éléments, {retenues} nouvelles annonces retenues")
        time.sleep(DELAI_ENTRE_REQUETES)

    # Append-only : on ajoute, on ne supprime jamais.
    base["annonces"].extend(nouvelles)
    base["derniere_collecte"] = maintenant
    sauvegarder_base(base)
    print(f"\nTotal : {len(nouvelles)} nouvelles annonces, {len(base['annonces'])} au total dans la base.")


if __name__ == "__main__":
    collecter()
