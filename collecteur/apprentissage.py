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

# Versant positif, aux mêmes seuils que le négatif. Il n'y en avait aucun :
# une seule candidature suffisait à installer un critère favorable définitif,
# ce qui est exactement le travers que l'on refuse au versant négatif.
MIN_CANDIDATURES_FORT = 3
TAUX_CANDIDATURES_FORT = 0.75
MIN_CANDIDATURES_FAIBLE = 2
TAUX_CANDIDATURES_FAIBLE = 0.50

POIDS_PENALITE = -2       # motif proche des refus
POIDS_FAVORABLE_FAIBLE = 2
POIDS_FAVORABLE_FORT = 4

# En dessous de ce score, l'annonce n'est pas masquée mais signalée : c'est la
# troisième issue, celle qui évite de trancher sur un faisceau d'indices encore
# mince. Seules les règles d'exclusion, elles, masquent vraiment.
SEUIL_A_EXAMINER = -4

# --- Extraction des caractéristiques ---------------------------------------

# Familles d'appareils : c'est souvent l'appareil, plus que le pays, qui décide.
APPAREILS = re.compile(
    r"\b(A2\d0|A3[1-8]0|B?7[0-8]7|E1[0-9]5|E-?Jet|CRJ\d*|ATR\s?-?\d{2}|Q400|DHC-?\d|"
    r"C(?:essna)?\s?208|Caravan|PC-?12|PC-?24|King\s?Air|Citation|Falcon\s?\d*|"
    r"Global\s?\d*|Challenger\s?\d*|Gulfstream|G[5-8]\d0|Learjet|Phenom|Legacy|Praetor|"
    r"EC\d{3}|H1\d{2}|AW1\d{2}|S-?76|B(?:ell)?\s?4\d{2})\b",
    re.IGNORECASE,
)

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


    for critere in criteres_presents(texte):
        traits.add(f"marqueur:{critere}")

    # Critères extraits de la fiche complète lors de la collecte : expérience
    # exigée, licences, certificats, séniorité, contrat, secteur… C'est là que
    # se trouve l'essentiel de ce qui distingue deux annonces, le titre et
    # l'extrait n'en montrant qu'une vitrine.
    traits.update(annonce.get("criteres") or [])

    verdict = annonce.get("langue_exigee")
    if verdict:
        traits.add(f"langue:{verdict.get('nature')}/{verdict.get('source', 'citee')}")


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
        elif statut in ("Postule", "Refus"):
            # « Refus reçu » signale une candidature envoyée, donc un intérêt
            # manifeste : c'est l'employeur qui a dit non, pas l'utilisateur.
            # Ranger ces annonces ailleurs qu'avec les candidatures aurait privé
            # le veto de la moitié de ses preuves d'intérêt.
            candidatees.append(annonce)
        else:
            retenues.append(annonce)

    # Aucune sortie anticipée sur l'absence de refus : les deux versants sont
    # indépendants. Un utilisateur qui ne marque que des candidatures doit voir
    # ses critères favorables se construire, sans avoir à écarter quoi que ce
    # soit d'abord.
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

    # --- Versant positif, construit exactement comme le négatif -------------
    #
    # Deux ensembles distincts, jamais mélangés : un critère favorable naît des
    # candidatures, un critère défavorable des refus. Ils ne se compensent pas
    # à la construction — seul le score final les additionne.
    compte_candidatures: Counter[str] = Counter()
    for annonce in candidatees:
        compte_candidatures.update(caracteristiques(annonce))

    favorables: dict[str, dict] = {}
    for motif, retenu in compte_candidatures.items():
        total = retenu + compte_reste.get(motif, 0) + compte_refus.get(motif, 0)
        taux = retenu / total if total else 0.0
        preuve = {"candidatures": retenu, "total": total, "taux": round(taux, 2)}
        if retenu >= MIN_CANDIDATURES_FORT and taux >= TAUX_CANDIDATURES_FORT:
            favorables[motif] = {**preuve, "poids": POIDS_FAVORABLE_FORT}
        elif retenu >= MIN_CANDIDATURES_FAIBLE and taux >= TAUX_CANDIDATURES_FAIBLE:
            favorables[motif] = {**preuve, "poids": POIDS_FAVORABLE_FAIBLE}

    return {
        "exclusions": exclusions,
        "penalites": penalites,
        "favorables": favorables,
        # Le veto reste distinct des critères favorables : il protège dès la
        # première candidature, alors qu'un critère favorable exige d'être
        # confirmé. Protéger et valoriser ne demandent pas la même preuve.
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


def evaluer(annonce: dict, regles: dict) -> dict:
    """Confronte une annonce aux deux ensembles de critères appris.

    Renvoie le détail de la correspondance — quels critères favorables et
    défavorables sont présents, leur cumul, et l'issue qui en découle :
    « conserver », « examiner » ou « ecarter ». La troisième issue existe pour
    ne pas trancher sur un faisceau d'indices encore mince : l'annonce reste
    visible, simplement signalée.
    """
    traits = caracteristiques(annonce)

    exclusion = next((m for m in regles.get("exclusions", {}) if m in traits), None)
    positifs = [m for m in regles.get("favorables", {}) if m in traits]
    negatifs = [m for m in regles.get("penalites", {}) if m in traits]

    points = sum(regles["favorables"][m]["poids"] for m in positifs)
    points += POIDS_PENALITE * len(negatifs)

    if exclusion:
        issue = "ecarter"
    elif points <= SEUIL_A_EXAMINER:
        issue = "examiner"
    else:
        issue = "conserver"

    return {
        "issue": issue,
        "score": points,
        "exclusion": exclusion,
        "favorables": positifs,
        "defavorables": negatifs,
    }


def score(annonce: dict, regles: dict) -> int:
    """Score de pertinence seul, pour le tri."""
    return evaluer(annonce, regles)["score"]


def resume(regles: dict) -> str:
    """Rapport d'ajustement : quelles règles ont été déduites, et sur quelles preuves."""
    # Une seule candidature suffit à faire vivre le rapport : c'est l'absence
    # de toute décision qui le rend vide, pas l'absence de refus.
    if not regles.get("nb_refus") and not regles.get("nb_candidatures"):
        return "Aucune décision exportée : aucune règle apprise."

    lignes = [
        f"{regles['nb_refus']} annonce(s) refusée(s), "
        f"{regles['nb_candidatures']} candidature(s) analysée(s)."
    ]
    if regles.get("favorables"):
        lignes.append("CRITÈRES FAVORABLES (issus des candidatures envoyées) :")
        for motif, p in sorted(regles["favorables"].items(), key=lambda x: -x[1]["candidatures"]):
            lignes.append(
                f"  + {motif} (retenu {p['candidatures']} fois sur {p['total']}, "
                f"{p['taux']:.0%}, poids +{p['poids']})"
            )
    elif regles["nb_candidatures"]:
        lignes.append("Aucun critère favorable : aucun ne se répète assez d'une candidature à l'autre.")
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
