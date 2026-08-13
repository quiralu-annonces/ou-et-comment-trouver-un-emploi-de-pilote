#!/usr/bin/env python3
"""Collecteur de la veille mondiale d'offres d'emploi de pilote.

Interroge trois familles de sources — bourses d'emploi aéronautiques (flux RSS
du SNPI et de la FFVP), plan de site d'AllFlyingJobs, et les pages carrières des
compagnies suivies nommément (voir ``compagnies.py``) —, filtre les résultats
pertinents, traduit les titres en français, et alimente la base append-only
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compagnies import (  # noqa: E402
    compagnies_a_compter,
    compagnies_automatiques,
    compter_offres,
    offres_compagnie,
)
from filtres import motif_exclusion  # noqa: E402
from reseau import lire_flux_rss, nettoyer_html, telecharger  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "data" / "annonces.json"

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


# --- Sources ---------------------------------------------------------------
#
# Les flux Google News ont été retirés le 31 juillet 2026. Ils ne publiaient que
# des articles de presse : sur 423 entrées accumulées, 410 étaient des
# actualités, aucune n'était une offre à laquelle candidater. Un agrégateur de
# presse ne peut pas, par nature, produire des offres d'emploi.
#
# Ne restent que des sources qui publient réellement des postes à pourvoir.
#
# Non retenues, et pourquoi :
#   - FFA (ffa-aero.fr)  : son robots.txt interdit explicitement ClaudeBot et
#                          signale « ai-train=no ». Source à consulter à la main.
#   - Indeed             : renvoie 403 sur ses flux RSS.
#   - AviationJobSearch, LatestPilotJobs, JSfirm, Climbto350 : plus aucun flux.

# (nom, url, langue, région par défaut)
SOURCES = [
    (
        "SNPI — bourse à l'emploi (France)",
        "https://snpi.aero/offres-emploi/feed/",
        "fr",
        "Europe",
    ),
    (
        "FFVP — bourse à l'emploi (France)",
        "https://www.ffvp.fr/bourse-a-emploi/feed",
        "fr",
        "Europe",
    ),
]

# --- AllFlyingJobs : découverte par le plan du site ------------------------
# Le site n'expose pas de flux RSS mais publie un sitemap.xml horodaté, et son
# robots.txt l'annonce explicitement. On y lit les fiches de poste récentes,
# en respectant le Crawl-delay de 3 secondes qu'il impose.

AFJ_SITEMAP = "https://www.allflyingjobs.com/sitemap.xml"
AFJ_DELAI = 3.0            # Crawl-delay impose par robots.txt — ne pas réduire
AFJ_FENETRE_JOURS = 31     # inutile de lire ce que le filtre d'un mois écartera
AFJ_MAX_FICHES = 120       # plafond par exécution ; le reste est signalé, pas masqué

# Postes de pilotage repérables dans l'adresse de la fiche. Le site publie aussi
# des postes de mécanicien, d'ingénierie ou de service client, hors périmètre.
AFJ_SLUG_PILOTE = re.compile(
    r"(?:^|-)(pilot|pilots|first-officer|captain|captains|cadet|cadets"
    r"|instructor|instructors|copilot|copilots|fo|sic|pic)(?:-|$)",
    re.IGNORECASE,
)

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


def deviner_region(texte: str, region_defaut: str) -> str:
    texte_bas = texte.lower()
    for region, indices in INDICES_REGION.items():
        if any(indice in texte_bas for indice in indices):
            return region
    return region_defaut


def _balise(motif: str, texte: str) -> str:
    trouve = re.search(motif, texte, re.IGNORECASE | re.DOTALL)
    if not trouve:
        return ""
    return nettoyer_html(html.unescape(trouve.group(1)))


def lire_sitemap_allflyingjobs() -> list[dict]:
    """Liste les fiches de poste de pilotage récentes publiées par AllFlyingJobs.

    Chaque fiche porte un bloc JSON-LD ``JobPosting`` : on y lit la date de
    publication réelle et le lieu, ce qu'aucun flux de presse ne fournissait.
    """
    try:
        plan = telecharger(AFJ_SITEMAP).decode("utf-8", "replace")
    except Exception as erreur:  # noqa: BLE001
        print(f"  ÉCHEC du plan de site ({erreur})", file=sys.stderr)
        return []

    limite = datetime.now(timezone.utc) - timedelta(days=AFJ_FENETRE_JOURS)
    candidates: list[tuple[datetime, str]] = []
    for lien, horodatage in re.findall(r"<loc>(.*?)</loc>\s*<lastmod>(.*?)</lastmod>", plan):
        if "/jobs/" not in lien:
            continue
        if not AFJ_SLUG_PILOTE.search(lien.rsplit("/jobs/", 1)[-1]):
            continue
        try:
            modifie = datetime.fromisoformat(horodatage)
        except ValueError:
            continue
        if modifie >= limite:
            candidates.append((modifie, lien))

    candidates.sort(reverse=True)
    total = len(candidates)
    if total > AFJ_MAX_FICHES:
        print(f"  {total} fiches récentes ; les {AFJ_MAX_FICHES} plus fraîches sont lues "
              f"cette fois, {total - AFJ_MAX_FICHES} le seront à la prochaine exécution")
        candidates = candidates[:AFJ_MAX_FICHES]
    else:
        print(f"  {total} fiche(s) de pilotage récente(s) à lire")

    items = []
    for modifie, lien in candidates:
        try:
            page = telecharger(lien).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 — une fiche illisible ne bloque pas les autres
            time.sleep(AFJ_DELAI)
            continue

        titre = _balise(r"<h1[^>]*>(.*?)</h1>", page)
        if not titre:
            time.sleep(AFJ_DELAI)
            continue
        lieu = _balise(r'"addressLocality"\s*:\s*"(.*?)"', page)
        pays = _balise(r'"addressCountry"\s*:\s*"(.*?)"', page)
        date_pub = _balise(r'"datePosted"\s*:\s*"(.*?)"', page) or modifie.isoformat()
        extrait = _balise(r'name="description"\s+content="(.*?)"', page)
        extrait = re.sub(r"^Pilot job vacancy details:\s*", "", extrait)[:400]

        items.append(
            {
                "titre": f"{titre} — {lieu}" if lieu else titre,
                "lien": lien,
                "date_publication": date_pub,
                "extrait": extrait,
                "media": "",
                "indice_region": f"{lieu} {pays}",
            }
        )
        time.sleep(AFJ_DELAI)
    return items


def est_pertinent(titre: str, extrait: str, bourse_emploi: bool = False) -> bool:
    """Le poste relève-t-il du pilotage ?

    Sur une bourse d'emploi, chaque page EST une offre : exiger en plus un mot
    de recrutement dans le titre n'a aucun sens et rejetait des offres valides
    (« DIRECT ENTRY CAPTAIN A320 IN COPENHAGEN » n'en contient aucun). Le test
    de recrutement ne sert qu'aux sources généralistes, pour distinguer une
    offre d'un article — il reste donc appliqué à elles seules.
    """
    champ = f"{titre} {extrait}"
    if not MOTS_PILOTE.search(champ):
        return False
    return bourse_emploi or bool(MOTS_RECRUTEMENT.search(champ))


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
    return {"annonces": [], "compagnies": {}, "derniere_collecte": None}


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
    lots: list[tuple[str, str, str, list[dict]]] = []

    for nom_source, url, langue, region_defaut in SOURCES:
        print(f"Source : {nom_source}")
        try:
            lots.append((nom_source, langue, region_defaut, lire_flux_rss(telecharger(url))))
        except Exception as erreur:  # noqa: BLE001 — une source en panne ne bloque pas les autres
            print(f"  ÉCHEC ({erreur})", file=sys.stderr)
        time.sleep(DELAI_ENTRE_REQUETES)

    print("Source : AllFlyingJobs (plan du site)")
    lots.append(("AllFlyingJobs", "en", "Monde", lire_sitemap_allflyingjobs()))

    # Les compagnies suivies nommément. Celles dont la page carrières n'est pas
    # moissonnable (mode « manuel ») ne sont pas interrogées ici : elles sont
    # publiées sur le site comme liste à consulter à la main.
    print("Sources : pages carrières des compagnies suivies")
    for compagnie in compagnies_automatiques():
        try:
            offres = offres_compagnie(compagnie)
        except Exception as erreur:  # noqa: BLE001 — un site en panne ne bloque pas les autres
            print(f"  ÉCHEC {compagnie['nom']} ({erreur})", file=sys.stderr)
            offres = []
        lots.append((compagnie["nom"], "fr", compagnie["region"], offres))
        time.sleep(DELAI_ENTRE_REQUETES)

    for nom_source, langue, region_defaut, items in lots:
        # Toutes les sources retenues sont des bourses d'emploi.
        bourse_emploi = True
        retenues = 0
        ecartees: dict[str, int] = {}
        for item in items:
            if not est_pertinent(item["titre"], item["extrait"], bourse_emploi):
                continue
            # Garde-fou : seules les offres d'emploi correspondant au profil
            # recherché entrent dans la base — au moins un des sept marqueurs
            # (pilote/copilote, entry level, 300 h de vol, anglais niveau 4,
            # non type rated, EASA ATPL, first officer). Si une source de presse
            # est réintroduite un jour, ses articles seront écartés ici plutôt
            # que de polluer la base comme auparavant.
            motif = motif_exclusion(
                {"lien": item["lien"], "titre_original": item["titre"], "extrait": item["extrait"]}
            )
            if motif:
                ecartees[motif] = ecartees.get(motif, 0) + 1
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
                # Le lieu tiré du JSON-LD, quand il existe, est bien plus fiable
                # pour situer l'offre que le seul texte du titre.
                "region": deviner_region(
                    f"{item.get('indice_region', '')} {item['titre']} {item['extrait']}",
                    region_defaut,
                ),
                "date_publication": item["date_publication"],
                "extrait": item["extrait"],
                "premiere_collecte": maintenant,
            }
            nouvelles.append(annonce)
            ids_connus.add(identifiant)
            titres_connus.add(cle_titre)
            retenues += 1
        motifs = {
            "actualite": "pas une offre",
            "nationalite": "nationalité exigée non détenue",
            "langue": "3e langue réclamée",
            "criteres": "aucun marqueur du profil recherché",
        }
        detail = ", ".join(f"{n} {motifs.get(m, m)}" for m, n in sorted(ecartees.items()))
        # Le nom de la source figure sur la ligne : avec une vingtaine de lots,
        # un simple décompte ne disait plus de quoi il parlait.
        print(
            f"  {nom_source} : {len(items)} élément(s), {retenues} offre(s) retenue(s), "
            f"{sum(ecartees.values())} écartée(s)" + (f" — {detail}" if detail else "")
        )

    # Portails dont les intitulés sont illisibles : on relève au moins combien
    # d'offres y sont ouvertes, pour que le site le dise à côté du lien.
    print("Compteurs : portails à intitulés illisibles")
    compteurs: dict[str, dict] = {}
    for compagnie in compagnies_a_compter():
        try:
            nombre = compter_offres(compagnie)
        except Exception as erreur:  # noqa: BLE001 — un portail en panne ne bloque pas la collecte
            print(f"  ÉCHEC {compagnie['nom']} ({erreur})", file=sys.stderr)
            continue
        compteurs[compagnie["nom"]] = {"offres_ouvertes": nombre, "releve_le": maintenant}
        print(f"  {compagnie['nom']} : {nombre} offre(s) ouverte(s)")
        time.sleep(DELAI_ENTRE_REQUETES)

    # Append-only : on ajoute, on ne supprime jamais.
    base["annonces"].extend(nouvelles)
    # Un relevé qui échoue ne doit pas effacer le précédent : on fusionne.
    base["compagnies"] = {**base.get("compagnies", {}), **compteurs}
    base["derniere_collecte"] = maintenant
    sauvegarder_base(base)
    print(f"\nTotal : {len(nouvelles)} nouvelles annonces, {len(base['annonces'])} au total dans la base.")


if __name__ == "__main__":
    collecter()
