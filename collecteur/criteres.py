#!/usr/bin/env python3
"""Extraction des critères d'une annonce lue en entier.

Le collecteur télécharge déjà le texte complet de chaque fiche — c'était pour
l'examen linguistique — puis le jetait. Ce module en tire les critères qui
caractérisent réellement un poste : expérience exigée, licences,
qualifications, certificats, langues, séniorité, contrat, responsabilités,
secteur d'activité.

**Chaque critère porte sa modalité.** « 1500 heures minimum » et « 1500 heures
appréciées » n'engagent pas le candidat de la même façon ; « anglais
obligatoire » et « anglais serait un plus » non plus. Le mécanisme qui
distinguait déjà l'exigence de l'atout pour les langues est ici généralisé à
toutes les familles.

**Les valeurs numériques sont regroupées par tranches.** Sans cela, « 1500 h »,
« 1800 h » et « 2000 h » seraient trois critères distincts, chacun trop rare
pour qu'un apprentissage y voie quoi que ce soit. Regroupées, elles disent la
même chose : un poste demandant plus de 1500 heures.

**Ni la compagnie ni la source n'apparaissent ici**, conformément à la règle
posée : écarter une annonce juge son contenu, pas l'employeur qui la publie.
Aucune famille ne capte de nom propre.

Chaque critère est rendu sous la forme ``famille:valeur|modalite``, par exemple
``licence:ATPL|exigence``. Cette forme canonique se compte, se compare entre
annonces, et se lit encore à l'œil nu dans un rapport.
"""

from __future__ import annotations

import re

from filtres import ATOUT, EXIGENCE

# Version de l'extracteur. À incrémenter dès que les motifs changent : le
# collecteur relit alors les annonces analysées par une version antérieure,
# comme il le fait déjà pour l'examen linguistique.
VERSION_ANALYSE_CRITERES = 5

# Bornes de phrase. Une fiche de poste énumère ses exigences en puces ou en
# phrases courtes : chacune qualifie son propre critère.
FIN_DE_PHRASE = re.compile(r"[.;:!?\n\r•·|]|\s-\s|\s–\s")

# Garde-fou : une « phrase » sans ponctuation ne doit pas absorber la fiche
# entière.
PORTEE_MAX = 220


def phrase_autour(texte: str, debut: int, fin: int) -> tuple[str, int]:
    """Phrase contenant le critère, bornée par la ponctuation.

    Une simple fenêtre de caractères ne convient pas : dans « 3000 hours would
    be a plus. CPL/IR required. », la licence se trouve à trente caractères de
    « plus » et héritait de sa modalité. Chaque exigence doit être jugée sur sa
    propre phrase, pas sur celle d'à côté.
    """
    gauche = texte.rfind("\n", max(0, debut - PORTEE_MAX), debut)
    for sep in FIN_DE_PHRASE.finditer(texte, max(0, debut - PORTEE_MAX), debut):
        gauche = max(gauche, sep.end())
    if gauche < 0:
        gauche = max(0, debut - PORTEE_MAX)

    droite = len(texte)
    sep = FIN_DE_PHRASE.search(texte, fin, min(len(texte), fin + PORTEE_MAX))
    if sep:
        droite = sep.start()
    else:
        droite = min(len(texte), fin + PORTEE_MAX)
    return texte[gauche:droite], gauche


def modalite(texte: str, debut: int, fin: int) -> str:
    """« exigence », « atout » ou « mention » pour le critère situé en [debut, fin].

    Le qualificatif retenu est **le plus proche du critère**, pas le premier
    trouvé. Une phrase en énumère souvent deux : « 5 years experience required,
    10 years appreciated » contient un mot d'exigence et un mot d'atout, et
    faire gagner l'un des deux systématiquement se trompe une fois sur deux.
    La proximité, elle, rattache chaque qualificatif au chiffre qu'il qualifie.

    En l'absence des deux, on parle de simple « mention » — l'annonce cite le
    critère sans dire ce qu'elle en attend.
    """
    phrase, decalage = phrase_autour(texte, debut, fin)
    gauche, droite = debut - decalage, fin - decalage

    meilleur: tuple[int, str] | None = None
    for motif, nature in ((ATOUT, "atout"), (EXIGENCE, "exigence")):
        for trouve in re.finditer(motif, phrase, re.IGNORECASE):
            if trouve.start() < droite and trouve.end() > gauche:
                distance = 0  # le qualificatif chevauche le critère
            else:
                distance = min(abs(trouve.start() - droite), abs(gauche - trouve.end()))
            if meilleur is None or distance < meilleur[0]:
                meilleur = (distance, nature)
    return meilleur[1] if meilleur else "mention"


# --- Expérience -------------------------------------------------------------

HEURES = re.compile(
    r"(\d{2,5})\s*(?:\+\s*)?(?:h\b|hrs?\b|hours?\b|heures?\b)"
    r"(?:[^.;\n]{0,40}?(?:flight|flying|vol|total|command|\bPIC\b|\bSIC\b|type))?"
    r"|(?:flight|flying|total|vol)\s*(?:time|hours?|heures?)?\s*[:\-–]?\s*(\d{2,5})",
    re.IGNORECASE,
)

ANNEES = re.compile(
    r"(\d{1,2})\s*(?:\+\s*)?(?:ans?\b|years?\b|yrs?\b)"
    r"[^.;\n]{0,40}?(?:exp[ée]rience|experience|anciennet[ée]|seniority)"
    r"|(?:exp[ée]rience|experience)[^.;\n]{0,40}?(\d{1,2})\s*(?:ans?\b|years?\b|yrs?\b)",
    re.IGNORECASE,
)

# Tranches d'heures de vol : les paliers qui séparent réellement les postes.
TRANCHES_HEURES = ((500, "0-500"), (1500, "500-1500"), (3000, "1500-3000"), (10**9, "3000+"))
TRANCHES_ANNEES = ((2, "0-2"), (5, "2-5"), (10, "5-10"), (10**9, "10+"))


def _tranche(valeur: int, tranches) -> str:
    for plafond, libelle in tranches:
        if valeur < plafond:
            return libelle
    return tranches[-1][1]


def _retenir_barre(mesures: list[tuple[int, str]]) -> tuple[int, str] | None:
    """Ne garde qu'une seule mesure d'expérience : la barre à franchir.

    Une fiche cite plusieurs volumes — total, commandant, sur type, instrument.
    Les retenir tous produisait des annonces réputées demander à la fois
    « 0-500 heures » et « 3000+ », c'est-à-dire ne rien caractériser du tout.

    On garde donc la barre la plus haute, celle qui situe réellement le poste :
    3000 heures exigées désignent un poste confirmé, 250 un poste d'accès. Une
    exigence l'emporte toujours sur un simple souhait, quel que soit le nombre :
    « 500 h requises, 3000 h appréciées » reste un poste ouvert à 500 heures.
    """
    if not mesures:
        return None
    fermes = [m for m in mesures if m[1] == "exigence"]
    return max(fermes or mesures, key=lambda m: m[0])


def _experience(texte: str) -> set[str]:
    heures: list[tuple[int, str]] = []
    for trouve in HEURES.finditer(texte):
        brut = trouve.group(1) or trouve.group(2)
        try:
            valeur = int(brut)
        except (TypeError, ValueError):
            continue
        # En deçà de 50 h, c'est une durée de stage ou un volume mensuel, pas
        # une expérience exigée.
        if valeur < 50:
            continue
        heures.append((valeur, modalite(texte, trouve.start(), trouve.end())))

    annees: list[tuple[int, str]] = []
    for trouve in ANNEES.finditer(texte):
        brut = trouve.group(1) or trouve.group(2)
        try:
            valeur = int(brut)
        except (TypeError, ValueError):
            continue
        if valeur < 1 or valeur > 40:
            continue
        annees.append((valeur, modalite(texte, trouve.start(), trouve.end())))

    traits: set[str] = set()
    barre = _retenir_barre(heures)
    if barre:
        traits.add(f"experience:heures:{_tranche(barre[0], TRANCHES_HEURES)}|{barre[1]}")
    barre = _retenir_barre(annees)
    if barre:
        traits.add(f"experience:annees:{_tranche(barre[0], TRANCHES_ANNEES)}|{barre[1]}")
    return traits


# --- Familles repérées par mots-clés ---------------------------------------
#
# Chaque famille associe un libellé canonique à son motif. Les libellés sont
# volontairement stables : ce sont eux qui se comptent d'une annonce à l'autre.

LICENCES = {
    "ATPL": r"\bATPL\b|airline\s+transport\s+pilot\s+licen[cs]e",
    "ATPL gelé": r"frozen\s*ATPL|ATPL\s*(?:gel[ée]e?|th[ée]orique)",
    "CPL": r"\bCPL\b|commercial\s+pilot\s+licen[cs]e",
    "MPL": r"\bMPL\b|multi[\s-]?crew\s+pilot\s+licen[cs]e",
    "IR": r"\bIR\b|instrument\s+rating|qualification\s+de\s+vol\s+aux\s+instruments",
    "EASA": r"\bEASA\b|\bAESA\b|part[\s-]?FCL",
    "FAA": r"\bFAA\b",
    "licence nationale": r"\bGCAA\b|\bCAAC\b|\bDGCA\b|\bCASA\b|\bTCCA\b|\bANAC\b|\bDGAC\b",
}

CERTIFICATS = {
    "classe 1": r"class\s*(?:1|i)\b[^.;\n]{0,25}medical|certificat\s+m[ée]dical\s+(?:de\s+)?classe\s*1|"
                r"medical\s+(?:certificate\s+)?class\s*(?:1|i)\b",
    "MCC": r"\bMCC\b|multi[\s-]?crew\s+co[\s-]?operation",
    "UPRT": r"\bUPRT\b|upset\s+prevention",
    "ETOPS": r"\bETOPS\b",
    "basse visibilité": r"\bLVO\b|low\s+visibility|CAT\s*(?:II|III|2|3)\b",
    "marchandises dangereuses": r"dangerous\s+goods|marchandises\s+dangereuses|\bDGR\b",
    "RVSM": r"\bRVSM\b|\bMNPS\b|\bPBN\b|\bRNP\b",
    "CRM": r"\bCRM\b|crew\s+resource\s+management",
}

QUALIFICATIONS = {
    "de type non requise": r"non[\s-]*type[\s-]*rated|no\s+type[\s-]*rating|"
                           r"type[\s-]*rating\s+(?:is\s+)?not\s+(?:required|needed)|"
                           r"sans\s+qualification\s+de\s+type",
    "de type à détenir": r"current\s+type\s+rating|qualification\s+de\s+type\s+en\s+cours|"
                         r"valid\s+type\s+rating|type[\s-]?rated\s+on",
    "de type financée": r"type\s+rating\s+(?:course|training)\s+provided|"
                        r"qualification\s+(?:de\s+type\s+)?financ[ée]|bond(?:ed)?\s+type\s+rating|"
                        r"formation\s+prise\s+en\s+charge",
}

SENIORITE = {
    "débutant": r"entry[\s-]*level|ab[\s-]*initio|low[\s-]*hours?|no\s+experience|d[ée]butant|cadet",
    "confirmé": r"exp[ée]riment[ée]|experienced|confirm[ée]|\bsenior\b",
    "entrée directe commandant": r"direct\s+entry\s+captain|\bDEC\b|commandant\s+de\s+bord\s+en\s+entr[ée]e\s+directe",
}

CONTRATS = {
    "CDI": r"\bCDI\b|permanent\s+(?:contract|position|role)|dur[ée]e\s+ind[ée]termin[ée]e",
    "CDD": r"\bCDD\b|fixed[\s-]?term|temporary\s+contract|dur[ée]e\s+d[ée]termin[ée]e|saisonnier|seasonal",
    "indépendant": r"freelance|contractor|self[\s-]?employed|ind[ée]pendant|\bB2B\b",
    "bénévole": r"b[ée]n[ée]vole|volunteer|non\s+r[ée]mun[ée]r|unpaid",
    "temps partiel": r"temps\s+partiel|part[\s-]?time",
    "expatriation": r"expatri|relocation|logement\s+fourni|accommodation\s+provided|"
                    r"permis\s+de\s+travail|work\s+permit|visa\s+sponsor",
}

RESPONSABILITES = {
    "encadrement": r"chef\s+pilote|chief\s+pilot|head\s+of|postholder|responsable\s+des\s+op[ée]rations|"
                   r"fleet\s+manager|directeur|manager\b",
    "instruction": r"instructeur|instructor|\bTRI\b|\bSFI\b|\bFI\b\b|formation\s+des\s+[ée]quipages",
    "contrôle": r"\bTRE\b|\bSFE\b|examinateur|examiner|contr[ôo]le\s+en\s+ligne|line\s+check",
    "sécurité": r"\bSGS\b|safety\s+manager|s[ée]curit[ée]\s+des\s+vols|flight\s+safety",
}

SECTEURS = {
    "transport de passagers": r"transport\s+de\s+passagers|passenger\s+(?:airline|operation|transport)|"
                              r"compagnie\s+r[ée]guli[èe]re|scheduled\s+(?:service|airline)",
    "fret": r"\bfret\b|cargo|freight|colis",
    "aviation d'affaires": r"business\s+aviation|aviation\s+d'affaires|corporate\s+aviation|"
                           r"\bVIP\b|jet\s+priv|private\s+jet|executive\s+aviation",
    "travail aérien": r"travail\s+a[ée]rien|[ée]pandage|agricole|spraying|surveillance\s+a[ée]rienne|"
                      r"calibration|photogramm[ée]tri|largage|remorquage|banderole",
    "secours et sanitaire": r"\bHEMS\b|\bEVASAN\b|medevac|air\s+ambulance|sanitaire|\bSAR\b|"
                            r"search\s+and\s+rescue|sauvetage",
    "formation": r"\b[ée]cole\b|\bATO\b|\bFTO\b|flight\s+school|acad[ée]mie|academy|centre\s+de\s+formation",
    "offshore": r"offshore|plateforme\s+p[ée]troli|oil\s+and\s+gas",
    "humanitaire": r"humanitaire|humanitarian|\bONU\b|\bUNHAS\b|\bICRC\b|\bMSF\b",
}

# Nature de l'activité. Complète les secteurs : deux postes de transport de
# passagers n'ont rien à voir selon qu'ils se volent de nuit sur long-courrier
# ou en régional de jour.
ACTIVITES = {
    "hélicoptère": r"h[ée]licopt[èe]re|helicopter|rotorcraft|voilure\s+tournante",
    "planeur": r"planeur|glider|vol\s+[àa]\s+voile|remorqueur",
    "ULM": r"\bULM\b|microlight|ultralight",
    "hydravion": r"hydravion|seaplane|floatplane|amphibie",
    "brousse": r"brousse|bush\s+pilot|piste\s+sommaire|unpaved",
    "militaire": r"militaire|military|d[ée]fense|defence|arm[ée]e",
    "essais en vol": r"essais\s+en\s+vol|test\s+pilot|flight\s+test",
    "lutte contre l'incendie": r"incendie|firefight|bombardier\s+d'eau|water\s+bomb",
    "régional": r"r[ée]gional|regional|court[\s-]?courrier|short[\s-]?haul|commuter",
    "long-courrier": r"long[\s-]?courrier|long[\s-]?haul|widebody|gros[\s-]?porteur",
    "charter": r"\bcharter\b|\bACMI\b|wet[\s-]?lease|affr[êe]tement",
    "vols de nuit": r"\bde\s+nuit\b|night\s+(?:flight|duty|operation|shift)|nachtflug",
    "rotation imposée": r"rotation|roster|\b\d{1,2}\s*/\s*\d{1,2}\b\s*(?:jours|days|pattern)",
    "base libre": r"commut|navette\s+[ée]quipage|base\s+libre|home\s+base\s+flexible",
    "astreinte": r"astreinte|standby|on[\s-]?call|r[ée]serve\s+op[ée]rationnelle",
}

FAMILLES = {
    "activite": ACTIVITES,
    "licence": LICENCES,
    "certificat": CERTIFICATS,
    "qualification": QUALIFICATIONS,
    "seniorite": SENIORITE,
    "contrat": CONTRATS,
    "responsabilite": RESPONSABILITES,
    "secteur": SECTEURS,
}

# --- Langues ----------------------------------------------------------------

NIVEAU_LANGUE = re.compile(
    r"(anglais|english|fran[çc]ais|french|espagnol|spanish|allemand|german|"
    r"arabe|arabic|chinois|chinese|mandarin|portugais|portuguese|italien|italian|"
    r"n[ée]erlandais|dutch|russe|russian)"
    r"[^.;\n]{0,45}?(?:level|niveau|\bELP\b)\s*\.?\s*([456])"
    r"|(?:level|niveau|\bELP\b)\s*\.?\s*([456])[^.;\n]{0,45}?"
    r"(anglais|english|fran[çc]ais|french|espagnol|spanish|allemand|german|"
    r"arabe|arabic|chinois|chinese|mandarin|portugais|portuguese|italien|italian|"
    r"n[ée]erlandais|dutch|russe|russian)",
    re.IGNORECASE,
)

NORMALISATION_LANGUE = {
    "english": "anglais", "french": "francais", "français": "francais", "francais": "francais",
    "spanish": "espagnol", "german": "allemand", "arabic": "arabe",
    "chinese": "chinois", "mandarin": "chinois", "portuguese": "portugais",
    "italian": "italien", "dutch": "neerlandais", "néerlandais": "neerlandais",
    "neerlandais": "neerlandais", "russian": "russe",
}


def _langues(texte: str) -> set[str]:
    traits: set[str] = set()
    for trouve in NIVEAU_LANGUE.finditer(texte):
        langue = (trouve.group(1) or trouve.group(4) or "").lower()
        niveau = trouve.group(2) or trouve.group(3)
        if not langue or not niveau:
            continue
        langue = NORMALISATION_LANGUE.get(langue, langue)
        traits.add(
            f"langue:{langue}{niveau}|{modalite(texte, trouve.start(), trouve.end())}"
        )
    return traits


# --- Extraction complète ----------------------------------------------------


def extraire(texte: str) -> list[str]:
    """Critères d'une annonce, sous forme canonique ``famille:valeur|modalite``.

    Renvoie une liste triée : stable d'une exécution à l'autre, donc lisible
    dans un fichier suivi par Git, où un ordre aléatoire produirait des
    différences fantômes à chaque collecte.
    """
    if not texte:
        return []

    traits = _experience(texte) | _langues(texte)
    for famille, valeurs in FAMILLES.items():
        for libelle, motif in valeurs.items():
            trouve = re.search(motif, texte, re.IGNORECASE)
            if trouve:
                traits.add(
                    f"{famille}:{libelle}|{modalite(texte, trouve.start(), trouve.end())}"
                )
    return sorted(traits)


# --- Mesures chiffrées, pour confronter l'annonce à un profil --------------
#
# Les traits ci-dessus servent à l'apprentissage : ils se comptent. Les mesures
# ci-dessous servent à décider : elles se comparent. Un candidat détenant 290
# heures ne peut pas postuler à un poste en exigeant 1500, quelle que soit la
# fréquence de ce critère dans ses refus passés.

# Postes de maintenance. Le candidat en vient — dix ans, Part-66 B1 — et ces
# annonces lui correspondent parfaitement sans l'intéresser.
MAINTENANCE = re.compile(
    r"m[ée]canicien|technicien\s+a[ée]ronautique|maintenance\s+(?:technician|engineer|mechanic)|"
    r"aircraft\s+(?:technician|mechanic|engineer)|part[\s-]?66|\bA&P\b|\bAMT\b|\bLAE\b|"
    r"licensed\s+aircraft\s+engineer|avionics\s+technician|technicien\s+avionique|"
    r"line\s+maintenance|base\s+maintenance|atelier|\bCRS\b|airworthiness\s+review",
    re.IGNORECASE,
)

# Postes de pilotage. Leur seule présence suffit à conserver l'annonce, même si
# elle parle aussi de maintenance : un poste mixte convient au candidat.
PILOTAGE = re.compile(
    r"\bpilote?s?\b|\bpilots?\b|co-?pilot|copilote|first\s+officer|second\s+officer|"
    r"\bOPL\b|\bSIC\b|\bPIC\b|commandant\s+de\s+bord|captain|capitaine|"
    r"instructeur\s+de\s+vol|flight\s+instructor|\bFI\s*\(|cadet|[ée]l[èe]ve[\s-]pilote|"
    r"flight\s+crew|personnel\s+navigant\s+technique|\bPNT\b|\bATPL\b|\bCPL\b",
    re.IGNORECASE,
)

TYPE_RATING_EXIGE = re.compile(
    r"current\s+type\s+rating|valid\s+type\s+rating|type[\s-]?rated\s+on|"
    r"qualification\s+de\s+type\s+(?:en\s+cours|valide|requise)",
    re.IGNORECASE,
)


def mesures(texte: str) -> dict:
    """Valeurs chiffrées et natures de poste, pour comparaison à un profil.

    ``heures_min_exigees`` est le **plancher** des exigences, pas le plafond :
    une fiche qui propose un copilote à 250 h et un commandant à 3000 h reste
    accessible par le bas. Retenir le maximum aurait écarté toute annonce
    couvrant plusieurs postes.
    """
    if not texte:
        return {}

    exigees = []
    for trouve in HEURES.finditer(texte):
        brut = trouve.group(1) or trouve.group(2)
        try:
            valeur = int(brut)
        except (TypeError, ValueError):
            continue
        if valeur < 50:
            continue
        if modalite(texte, trouve.start(), trouve.end()) == "exigence":
            exigees.append(valeur)

    langues_exigees: dict[str, int] = {}
    for trouve in NIVEAU_LANGUE.finditer(texte):
        langue = (trouve.group(1) or trouve.group(4) or "").lower()
        niveau = trouve.group(2) or trouve.group(3)
        if not langue or not niveau:
            continue
        if modalite(texte, trouve.start(), trouve.end()) != "exigence":
            continue
        langue = NORMALISATION_LANGUE.get(langue, langue)
        langues_exigees[langue] = max(langues_exigees.get(langue, 0), int(niveau))

    return {
        "heures_min_exigees": min(exigees) if exigees else None,
        "heures_max_exigees": max(exigees) if exigees else None,
        "langues_exigees": langues_exigees,
        "type_rating_exige": bool(TYPE_RATING_EXIGE.search(texte)),
        "maintenance": bool(MAINTENANCE.search(texte)),
        "pilotage": bool(PILOTAGE.search(texte)),
    }


def libelle(trait: str) -> str:
    """Rend un critère lisible : ``licence:ATPL|exigence`` → « licence ATPL (exigée) »."""
    corps, _, mod = trait.partition("|")
    famille, _, valeur = corps.partition(":")
    valeur = valeur.replace(":", " ")
    suffixe = {"exigence": "exigé", "atout": "apprécié", "mention": "mentionné"}.get(mod, mod)
    return f"{famille} {valeur} ({suffixe})"
