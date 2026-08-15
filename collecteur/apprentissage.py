#!/usr/bin/env python3
"""Apprentissage des refus : déduire des règles de ce que l'utilisateur écarte.

Le site mémorise les décisions du visiteur dans son navigateur, où le
collecteur ne peut pas les lire. Le bouton « Exporter mes décisions » produit
donc un fichier que l'on dépose dans ``data/decisions.json`` ; ce module le lit
et en tire des règles de sélection.

L'export ne contient que des identifiants et des statuts, jamais de texte : les
annonces sont déjà en base, il suffit de les retrouver.

**Le danger de cet exercice est le surapprentissage.** Sur trois refus, une
machine conclut n'importe quoi : si les trois premiers rejets sont des postes
en Afrique, elle décide d'exclure l'Afrique, alors que c'était peut-être le
type d'appareil qui déplaisait. Trois garde-fous l'en empêchent :

1. *Un seuil de présence* — un motif doit se retrouver dans au moins
   ``MIN_REFUS_EXCLUSION`` annonces refusées. Un refus isolé ne fait pas loi.
2. *Un taux de refus* — il ne suffit pas qu'un motif soit fréquent chez les
   refusées, il doit être **rare ailleurs**. « Copilote » figure dans presque
   toutes les annonces, refusées comprises : ce n'est pas un motif de refus,
   c'est le métier.
3. *Un veto des candidatures* — un motif présent dans une annonce à laquelle
   l'utilisateur a postulé ne peut jamais devenir une règle d'exclusion,
   quelle que soit sa statistique. Ce qu'il a voulu ne peut pas être ce qu'il
   rejette.

Les motifs qui franchissent les trois seuils écartent l'annonce. Ceux qui n'en
franchissent qu'une partie ne font que la faire descendre dans la liste.

**Ni la compagnie ni la source ne sont jamais des motifs.** Écarter une annonce
juge son contenu — le poste, l'appareil, la mission, l'expérience exigée —, pas
l'employeur qui la publie ni la bourse d'emploi où elle a été trouvée. Refuser
quatre annonces d'un transporteur ne veut pas dire qu'on refuse ce transporteur :
sa cinquième offre peut être exactement le poste recherché.

Cette garantie ne repose pas sur une liste de noms à écarter — une telle liste
ignorerait toujours les petits employeurs — mais sur l'inverse : **seul un
vocabulaire décrivant le contenu du poste est appris**. Aucun nom propre ne peut
donc devenir un motif, qu'il soit connu ou non.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from filtres import criteres_presents, texte_annonce

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DECISIONS = RACINE / "data" / "decisions.json"

# --- Seuils ----------------------------------------------------------------

MIN_REFUS_EXCLUSION = 3     # présences minimales parmi les annonces refusées
TAUX_REFUS_EXCLUSION = 0.75  # part des annonces portant ce motif qui ont été refusées
MIN_REFUS_PENALITE = 2
TAUX_REFUS_PENALITE = 0.50

POIDS_PENALITE = -2   # points retirés par motif pénalisé
POIDS_BONUS = 1       # points ajoutés par motif présent dans une candidature

# --- Extraction des caractéristiques ---------------------------------------

# Familles d'appareils : c'est souvent l'appareil, plus que le pays, qui décide.
APPAREILS = re.compile(
    r"\b(A2\d0|A3[1-8]0|B?7[0-8]7|E1[0-9]5|E-?Jet|CRJ\d*|ATR\s?-?\d{2}|Q400|DHC-?\d|"
    r"C(?:essna)?\s?208|Caravan|PC-?12|PC-?24|King\s?Air|Citation|Falcon\s?\d*|"
    r"Global\s?\d*|Challenger\s?\d*|Gulfstream|G[5-8]\d0|Learjet|Phenom|Legacy|Praetor|"
    r"EC\d{3}|H1\d{2}|AW1\d{2}|S-?76|B(?:ell)?\s?4\d{2})\b",
    re.IGNORECASE,
)

CONTRATS = {
    "cdi": r"\bCDI\b|permanent\b|full[\s-]?time\s+permanent",
    "cdd": r"\bCDD\b|fixed[\s-]?term|temporary|saisonnier|seasonal",
    "freelance": r"freelance|contractor|self[\s-]?employed|ind[ée]pendant",
    "benevole": r"b[ée]n[ée]vole|volunteer|non\s+r[ée]mun[ée]r|unpaid",
    "temps_partiel": r"temps\s+partiel|part[\s-]?time|\b\d{2}\s?-\s?\d{2}\s?%",
}

# Nature de la mission. Ce vocabulaire est une **liste blanche** : seuls ces
# thèmes sont appris, jamais un mot quelconque de l'intitulé.
#
# Une liste noire de noms de compagnies ne suffisait pas. Elle ne peut pas
# connaître les petits employeurs : refuser quatre annonces de l'« Aéroclub du
# Pontreau » aurait produit la règle « pontreau », c'est-à-dire précisément le
# nom d'un employeur. En n'apprenant que sur un vocabulaire de contenu, aucun
# nom propre ne peut devenir un motif, connu ou non.
#
# Le prix à payer est réel : un thème absent de cette liste n'est pas appris.
# Il s'ajoute ici en une ligne le jour où il apparaît.
THEMES = {
    "fret": r"\bfret\b|cargo|freight|colis|courrier\s+postal",
    "medical": r"m[ée]dical|\bEVASAN\b|\bHEMS\b|ambulance|air\s+ambulance|sanitaire|"
               r"[ée]vacuation|medevac|patient",
    "secours": r"\bSAR\b|search\s+and\s+rescue|sauvetage|secours|recherche\s+et\s+sauvetage",
    "offshore": r"offshore|plateforme\s+p[ée]troli|oil\s+and\s+gas",
    "incendie": r"incendie|firefight|bombardier\s+d'eau|water\s+bomb|lutte\s+contre\s+le\s+feu",
    "travail_aerien": r"[ée]pandage|agricole|spraying|photo\s?grammetri|surveillance\s+a[ée]rienne|"
                      r"calibration|banderole|largage|parachut|remorquage",
    "charter": r"\bcharter\b|\bACMI\b|wet[\s-]?lease|affr[êe]tement",
    "affaires": r"affaires|business\s+aviation|corporate|\bVIP\b|jet\s+priv|private\s+jet|"
                r"executive\s+aviation",
    "regional": r"r[ée]gional|regional|court[\s-]?courrier|short[\s-]?haul|commuter",
    "long_courrier": r"long[\s-]?courrier|long[\s-]?haul|widebody|gros[\s-]?porteur",
    "helicoptere": r"h[ée]licopt[èe]re|helicopter|rotorcraft|voilure\s+tournante",
    "planeur": r"planeur|glider|vol\s+[àa]\s+voile|remorqueur",
    "ulm": r"\bULM\b|microlight|ultralight",
    "hydravion": r"hydravion|seaplane|floatplane|amphibie",
    "brousse": r"brousse|bush\s+pilot|piste\s+sommaire|unpaved|humanitaire|humanitarian|"
               r"\bONU\b|\bUN\b\s+mission",
    "militaire": r"militaire|military|d[ée]fense|defence|arm[ée]e",
    "ecole": r"[ée]cole|school|\bATO\b|\bFTO\b|acad[ée]mie|academy|formation\s+ab\s?initio",
    "essais": r"essais\s+en\s+vol|test\s+pilot|flight\s+test|r[ée]ception",
    "encadrement": r"chef\s+pilote|chief\s+pilot|responsable|manager|directeur|head\s+of|"
                   r"postholder|\bCDO\b|\bDGO\b",
    "nuit": r"\bde\s+nuit\b|night\s+(?:flight|duty|operation|shift)|nachtflug|vols?\s+de\s+nuit",
    "rotation": r"rotation|roster|\b\d{1,2}\s*/\s*\d{1,2}\b\s*(?:jours|days|pattern)?|"
                r"pattern\s+de\s+vol|bloc\s+de\s+jours",
    "expatriation": r"expatri|relocation|permis\s+de\s+travail|work\s+permit|visa\s+sponsor|"
                    r"logement\s+fourni|accommodation\s+provided",
    "commuting": r"commut|navette\s+[ée]quipage|base\s+libre|home\s+base\s+flexible",
    "astreinte": r"astreinte|standby|on[\s-]?call|r[ée]serve\s+op[ée]rationnelle",
}

POSTES = {
    "commandant": r"\bcapitaine|captain|commandant\b|\bPIC\b|\bCDB\b",
    "copilote": r"copilot|co-?pilote|first\s+officer|\bOPL\b|\bSIC\b",
    "instructeur": r"instructeur|instructor|\bTRI\b|\bTRE\b|\bSFI\b|\bFI\b",
    "simulateur": r"simulateur|simulator|\bFFS\b|synth[ée]tique|synthetic",
    "cadet": r"cadet|ab[\s-]?initio|entry[\s-]?level",
}


# Mots trop courants pour signaler quoi que ce soit. Ne servent qu'au rapport
# de signaux ci-dessous, jamais à une règle.
MOTS_COURANTS = {
    "pour", "avec", "dans", "des", "les", "une", "sur", "aux", "par", "chez", "sont",
    "the", "and", "for", "with", "our", "you", "your", "are", "job", "jobs", "from",
    "emploi", "poste", "postes", "recherche", "recrute", "offre", "offres", "aeroport",
    "aviation", "avion", "aircraft", "airlines", "airline", "flight", "vol", "vols",
    "pilote", "pilotes", "pilot", "pilots", "copilote", "officer", "temps", "plein",
    "full", "time", "type", "rated", "rating", "based", "base", "experience",
}


def _sans_accent(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in texte if not unicodedata.combining(c))


def signaux_non_appris(refusees: list[dict], retenues: list[dict], limite: int = 12) -> list[dict]:
    """Mots surreprésentés chez les annonces refusées, **sans aucun effet**.

    C'est la réponse au défaut de la liste blanche : un thème qu'elle ne
    contient pas — des rotations de nuit, un rythme particulier — reste
    invisible à l'apprentissage. Ce rapport le rend visible sans lui donner le
    droit d'écarter quoi que ce soit.

    La séparation est délibérée. Une règle qui masque une annonce peut coûter
    un poste sans qu'on le sache : elle mérite un vocabulaire contrôlé. Signaler
    qu'un mot revient souvent ne coûte rien — au pire, on aura montré un mot
    inutile. Rien ne justifie la même prudence des deux côtés.

    Les noms d'employeurs figureront dans cette liste : c'est sans danger,
    puisqu'elle n'agit pas. C'est au lecteur de distinguer ce qui décrit un
    poste de ce qui nomme une compagnie — jugement qu'aucune liste ne peut
    rendre à sa place.
    """
    if not refusees:
        return []

    def mots(annonce: dict) -> set[str]:
        titre = _sans_accent(
            f"{annonce.get('titre_fr', '')} {annonce.get('titre_original', '')}"
        ).lower()
        return {m for m in re.findall(r"[a-z]{4,}", titre) if m not in MOTS_COURANTS}

    compte_refus: Counter[str] = Counter()
    for annonce in refusees:
        compte_refus.update(mots(annonce))
    compte_reste: Counter[str] = Counter()
    for annonce in retenues:
        compte_reste.update(mots(annonce))

    # Ce qui est déjà couvert par le vocabulaire appris n'a rien à signaler.
    deja_couvert = set()
    for annonce in refusees:
        deja_couvert |= {t.split(":", 1)[1].lower() for t in caracteristiques(annonce)}

    signaux = []
    for mot, refus in compte_refus.items():
        if refus < MIN_REFUS_PENALITE or mot in deja_couvert:
            continue
        total = refus + compte_reste.get(mot, 0)
        taux = refus / total if total else 0.0
        if taux >= TAUX_REFUS_PENALITE:
            signaux.append({"mot": mot, "refus": refus, "total": total, "taux": round(taux, 2)})
    signaux.sort(key=lambda s: (-s["refus"], -s["taux"]))
    return signaux[:limite]


def caracteristiques(annonce: dict) -> set[str]:
    """Caractéristiques observables d'une annonce, servant de motifs candidats.

    On privilégie des traits structurés — région, appareil, type de poste,
    contrat — aux simples mots du titre. Sur quelques dizaines de décisions,
    un motif structuré se vérifie ; un mot isolé se retrouve par hasard.

    Ni la compagnie ni la bourse d'emploi n'y figurent : écarter une annonce
    juge son contenu, pas l'employeur qui la publie ni le site où elle a été
    trouvée.
    """
    texte = texte_annonce(annonce)
    traits = {f"region:{annonce.get('region', '?')}"}

    for appareil in APPAREILS.findall(texte):
        traits.add(f"appareil:{_sans_accent(appareil).upper().replace(' ', '').replace('-', '')}")

    for nom, motif in POSTES.items():
        if re.search(motif, texte, re.IGNORECASE):
            traits.add(f"poste:{nom}")

    for nom, motif in CONTRATS.items():
        if re.search(motif, texte, re.IGNORECASE):
            traits.add(f"contrat:{nom}")

    for critere in criteres_presents(texte):
        traits.add(f"marqueur:{critere}")

    verdict = annonce.get("langue_exigee")
    if verdict:
        traits.add(f"langue:{verdict.get('nature')}/{verdict.get('source', 'citee')}")

    for nom, motif in THEMES.items():
        if re.search(motif, texte, re.IGNORECASE):
            traits.add(f"theme:{nom}")

    return traits


# --- Lecture des décisions exportées ---------------------------------------


def charger_decisions(fichier: Path = FICHIER_DECISIONS) -> dict[str, str]:
    """Décisions exportées depuis les navigateurs, fusionnées.

    Le fichier accepte un export unique ou une liste d'exports : le lien ayant
    été partagé, plusieurs personnes peuvent contribuer leurs décisions.
    En cas de désaccord sur une même annonce, une candidature l'emporte sur un
    refus — l'intérêt manifeste prime sur le désintérêt.
    """
    if not fichier.exists():
        return {}
    try:
        brut = json.loads(fichier.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"  décisions illisibles ({fichier}) : apprentissage ignoré")
        return {}

    exports = brut if isinstance(brut, list) else [brut]
    priorite = {"Postule": 3, "Refus": 2, "Ecartee": 1}
    fusion: dict[str, str] = {}
    for export in exports:
        for identifiant, statut in (export.get("decisions") or {}).items():
            ancien = fusion.get(identifiant)
            if ancien is None or priorite.get(statut, 0) > priorite.get(ancien, 0):
                fusion[identifiant] = statut
    return fusion


# --- Déduction des règles ---------------------------------------------------


def deduire_regles(annonces: list[dict], decisions: dict[str, str]) -> dict:
    """Déduit les motifs à exclure et à pénaliser à partir des décisions.

    Renvoie un état complet — règles, motifs pénalisés, bonus et décomptes —
    pour que le rapport puisse justifier chaque règle par ses chiffres plutôt
    que de les asséner.
    """
    refusees, retenues, candidatees = [], [], []
    for annonce in annonces:
        statut = decisions.get(annonce["id"])
        if statut == "Ecartee":
            refusees.append(annonce)
        elif statut == "Postule":
            candidatees.append(annonce)
        else:
            retenues.append(annonce)

    if not refusees:
        return {
            "exclusions": {}, "penalites": {}, "bonus": set(),
            "nb_refus": 0, "nb_candidatures": len(candidatees),
        }

    compte_refus: Counter[str] = Counter()
    for annonce in refusees:
        compte_refus.update(caracteristiques(annonce))
    compte_reste: Counter[str] = Counter()
    for annonce in retenues:
        compte_reste.update(caracteristiques(annonce))

    # Veto : ce que l'utilisateur a voulu ne peut pas devenir un motif d'exclusion.
    proteges: set[str] = set()
    for annonce in candidatees:
        proteges |= caracteristiques(annonce)

    exclusions: dict[str, dict] = {}
    penalites: dict[str, dict] = {}
    for motif, refus in compte_refus.items():
        total = refus + compte_reste.get(motif, 0)
        taux = refus / total if total else 0.0
        preuve = {"refus": refus, "total": total, "taux": round(taux, 2)}
        if motif in proteges:
            continue
        if refus >= MIN_REFUS_EXCLUSION and taux >= TAUX_REFUS_EXCLUSION:
            exclusions[motif] = preuve
        elif refus >= MIN_REFUS_PENALITE and taux >= TAUX_REFUS_PENALITE:
            penalites[motif] = preuve

    return {
        "exclusions": exclusions,
        "penalites": penalites,
        "bonus": proteges,
        "nb_refus": len(refusees),
        "nb_candidatures": len(candidatees),
        "signaux": signaux_non_appris(refusees, retenues),
    }


def motif_appris(annonce: dict, regles: dict) -> str | None:
    """Premier motif d'exclusion appris que porte l'annonce, s'il y en a un."""
    traits = caracteristiques(annonce)
    for motif in regles.get("exclusions", {}):
        if motif in traits:
            return motif
    return None


def score(annonce: dict, regles: dict) -> int:
    """Score de pertinence : négatif si l'annonce ressemble aux refus passés."""
    traits = caracteristiques(annonce)
    total = 0
    for motif in regles.get("penalites", {}):
        if motif in traits:
            total += POIDS_PENALITE
    for motif in regles.get("bonus", set()):
        if motif in traits:
            total += POIDS_BONUS
    return total


def resume(regles: dict) -> str:
    """Rapport d'ajustement : quelles règles ont été déduites, et sur quelles preuves."""
    if not regles.get("nb_refus"):
        return "Aucune décision exportée : aucune règle apprise."

    lignes = [
        f"{regles['nb_refus']} annonce(s) refusée(s), "
        f"{regles['nb_candidatures']} candidature(s) analysée(s)."
    ]
    if regles["exclusions"]:
        lignes.append("Exclusions apprises :")
        for motif, p in sorted(regles["exclusions"].items(), key=lambda x: -x[1]["refus"]):
            lignes.append(f"  – {motif} (refusée {p['refus']} fois sur {p['total']}, {p['taux']:.0%})")
    else:
        lignes.append("Aucune exclusion : aucun motif ne franchit les seuils.")
    if regles["penalites"]:
        lignes.append("Motifs pénalisés (descendus dans la liste, jamais masqués) :")
        for motif, p in sorted(regles["penalites"].items(), key=lambda x: -x[1]["refus"]):
            lignes.append(f"  – {motif} (refusée {p['refus']} fois sur {p['total']}, {p['taux']:.0%})")
    if regles.get("signaux"):
        lignes.append("Signaux NON appris — aucun effet, à examiner :")
        for s in regles["signaux"]:
            lignes.append(f"  ? « {s['mot']} » ({s['refus']} de vos refus sur {s['total']}, {s['taux']:.0%})")
        lignes.append("    Si l'un décrit un contenu de poste et non une compagnie, il peut")
        lignes.append("    rejoindre THEMES et devenir un critère à part entière.")
    return "\n".join(lignes)
