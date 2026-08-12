#!/usr/bin/env python3
"""Filtres du master prompt, partagés par le collecteur et le générateur.

Deux exigences que le collecteur d'origine n'appliquait pas :

1. **Uniquement des offres d'emploi, jamais d'actualités.** Le collecteur
   interroge des flux Google News : par construction, il en revient des
   articles de presse. Un article intitulé « l'armée cherche le pilote d'un
   avion abattu » contient « pilote » et « cherche » — il passait donc le
   filtre de mots-clés d'origine, qui ne savait pas distinguer un article
   d'une offre.

   La distinction ne peut pas se faire sur les mots du titre : « Azul prévoit
   de recruter 446 pilotes » est une actualité, « Azul recrute des pilotes »
   serait une offre, et les deux titres se ressemblent. Le seul critère fiable
   est **la nature de la source** : une offre d'emploi est publiée sur un site
   d'emploi ou une page carrières, jamais sur un site de presse. On travaille
   donc par liste blanche d'origines, pas par liste noire de mots.

2. **Règle A du §5.1 de l'addendum — nationalité.** Une annonce exigeant une
   nationalité autre que française est écartée, quels que soient ses autres
   mérites.

3. **Critères requis (addendum du 12 août 2026).** Une annonce n'est retenue
   que si elle porte au moins un des huit marqueurs du profil recherché
   (pilote/copilote, entry level, minimum 300 heures de vol, anglais niveau 4,
   non type rated, EASA ATPL, first officer, instructeur/FI). Un poste de
   commandant de bord expérimenté ne porte aucun de ces marqueurs : il est
   écarté.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# --- 1. Origines reconnues comme publiant de véritables offres --------------

# Domaines de sites d'emploi, bourses fédérales et cabinets de recrutement.
DOMAINES_EMPLOI = (
    "snpi.aero", "ffvp.fr", "ffa-aero.fr", "ffplum.fr", "aeroclub.com",
    "allflyingjobs.com", "latestpilotjobs.com", "pilotassessments.com",
    "aviationjobsearch.com", "gooserecruitment.com", "pilotsglobal.com",
    "climbto350.com", "jsfirm.com", "aviationcv.com", "rishworthaviation.com",
    "brookfieldaviation.com", "sigma-aviation.com", "aeroprofessional.com",
    "flightdeckfriend.com", "pilotcareercentre.com", "avjobs.com",
    "indeed.com", "welcometothejungle.com", "apec.fr", "francetravail.fr",
    "pole-emploi.fr", "linkedin.com/jobs", "glassdoor.com",
    # Plateformes de gestion de candidatures utilisées par les compagnies
    "workday.com", "myworkdayjobs.com", "greenhouse.io", "lever.co",
    "smartrecruiters.com", "teamtailor.com", "hrmdirect.com", "icims.com",
    "successfactors.com", "taleo.net", "recruitee.com", "personio.de",
)

# Segments d'URL qui signalent une page d'offre ou une page carrières,
# quel que soit le domaine (utile pour les sites propres des compagnies).
CHEMINS_EMPLOI = (
    "/careers", "/career", "/jobs", "/job/", "/vacancy", "/vacancies",
    "/recruitment", "/recrutement", "/offres-emploi", "/offre-emploi",
    "/emploi", "/nous-rejoindre", "/join-us", "/work-with-us", "/hiring",
    "/empleo", "/vagas", "/carreira", "/stellenangebote", "/karriere",
    "/candidature", "/apply", "/opportunities", "/vacatures",
)

SOUS_DOMAINES_EMPLOI = (
    "careers.", "career.", "jobs.", "job.", "recruitment.", "emploi.",
    "carrieres.", "carrières.", "recrutement.",
)

# Agrégateurs de presse : une URL Google News ne pointe jamais vers une offre.
DOMAINES_PRESSE_CERTAINS = ("news.google.com", "nabdapp.com", "flipboard.com", "msn.com")


def _hote_et_chemin(lien: str) -> tuple[str, str]:
    try:
        u = urlparse(lien)
    except ValueError:
        return "", ""
    return (u.netloc or "").lower(), (u.path or "").lower()


def est_offre_emploi(lien: str) -> bool:
    """Vrai si l'URL provient d'une source qui publie des offres d'emploi.

    Critère volontairement strict : dans le doute, on écarte. Mieux vaut
    manquer une offre — les autres sources la rapporteront — que présenter un
    article de presse comme une offre, ce qui fait perdre du temps à chaque
    consultation et discrédite l'outil.
    """
    hote, chemin = _hote_et_chemin(lien)
    if not hote:
        return False
    if any(d in hote for d in DOMAINES_PRESSE_CERTAINS):
        return False
    complet = hote + chemin
    if any(d in complet for d in DOMAINES_EMPLOI):
        return True
    if hote.startswith(SOUS_DOMAINES_EMPLOI):
        return True
    return any(seg in chemin for seg in CHEMINS_EMPLOI)


# --- 2. Règle A : nationalité exigée autre que française --------------------

# Formulations explicites d'une exigence de nationalité. On ne bloque que sur
# une exigence claire : une simple mention de pays ne suffit pas, sinon toute
# annonce localisée à l'étranger serait écartée à tort.
NATIONALITE_EXIGEE = re.compile(
    r"(?:nationalit[ée]s?|citizenship|citizens?|nationals?|ressortissants?)"
    r"[^.;\n]{0,60}"
    r"(?:saoudien|saudi|k[ae]zakh|émirati|emirati|qatari|koweït|kuwaiti|omani|"
    r"bahrein|bahraini|chinois|chinese|indien|indian|malais|malaysian|"
    r"indon[ée]sien|indonesian|philippin|filipino|thai|vietnamien|vietnamese|"
    r"turc|turkish|russe|russian|brésilien|brazilian|marocain|moroccan|"
    r"[ée]gyptien|egyptian|nig[ée]rian|nigerian|k[ée]nyan|kenyan)"
    r"|(?:saudi|emirati|qatari|kuwaiti|omani|bahraini|kazakhstani|chinese|indian|"
    r"malaysian|indonesian|filipino|thai|vietnamese|turkish|russian|brazilian|"
    r"moroccan|egyptian|nigerian|kenyan)\s+(?:nationals?|citizens?|passport holders?)"
    r"|مواطن(?:ي|ين)?\s*سعودي|سعودي\s*الجنسية|الجنسية\s*السعودية",
    re.IGNORECASE,
)

# Le candidat est français : ces exigences-là ne bloquent pas.
NATIONALITE_ACCEPTEE = re.compile(
    r"fran[çc]ais|french|union européenne|european union|\beu\b|eea|"
    r"espace économique européen|ressortissant communautaire",
    re.IGNORECASE,
)


def nationalite_bloquante(texte: str) -> bool:
    """Vrai si l'annonce exige une nationalité que le candidat ne détient pas.

    Applique la règle A du §5.1 de l'addendum. Si l'annonce mentionne aussi la
    France ou l'Union européenne parmi les nationalités acceptées, elle n'est
    pas bloquée : c'est le cas des offres ouvertes à plusieurs nationalités.
    """
    if not texte:
        return False
    if not NATIONALITE_EXIGEE.search(texte):
        return False
    return not NATIONALITE_ACCEPTEE.search(texte)


# --- 3. Critères requis : au moins un doit figurer dans l'annonce -----------
#
# Sept marqueurs décrivent le profil visé. Chacun est reconnu par ses
# formulations courantes en anglais comme en français, l'annonce d'origine
# n'étant pas toujours traduite au moment du filtrage.
#
# Le rôle de ce filtre est d'écarter ce qui ne s'adresse pas à un pilote en
# début de carrière : commandant de bord expérimenté, mécanicien navigant,
# poste au sol. Un seul marqueur suffit — les annonces les plus succinctes
# n'énoncent que le titre du poste.

# Un plafond est nécessaire pour le critère « minimum 300 heures de vol » :
# sans lui, « minimum 5000 hours total time » — l'exact opposé du profil —
# satisferait le critère. 500 h laisse la marge des annonces qui demandent
# « 300 to 500 hours » sans laisser passer les postes expérimentés.
SEUIL_HEURES_VOL = 500

# Un nombre d'heures n'est un critère de vol que s'il est adossé à un mot de
# vol : sans cela, « 40 hours per week » serait compté comme expérience.
HEURES_DE_VOL = re.compile(
    r"(?:flight|flying|total|vol|heures\s+de)\s*(?:time|hours?|heures?)?\s*[:\-–]?\s*(\d{2,5})\s*(?:\+\s*)?"
    r"(?:h\b|hrs?\b|hours?\b|heures?\b)"
    r"|(\d{2,5})\s*(?:\+\s*)?(?:h\b|hrs?\b|hours?\b|heures?\b)\s*(?:of\s+)?(?:total\s+)?"
    r"(?:flight|flying|vol|total\s+time)",
    re.IGNORECASE,
)


def _heures_de_vol_accessibles(texte: str) -> bool:
    """Vrai si l'annonce annonce une expérience exigée de l'ordre de 300 heures."""
    for trouve in HEURES_DE_VOL.finditer(texte):
        brut = trouve.group(1) or trouve.group(2)
        try:
            heures = int(brut)
        except (TypeError, ValueError):
            continue
        if heures <= SEUIL_HEURES_VOL:
            return True
    return False


CRITERES_REQUIS: tuple[tuple[str, object], ...] = (
    (
        "Pilote / copilote",
        re.compile(r"\b(?:pilote?s?|co-?pilote?s?|piloto)\b", re.IGNORECASE),
    ),
    (
        "Entry level",
        re.compile(
            r"entry[\s-]*level|ab[\s-]*initio|low[\s-]*hours?|no\s+experience|"
            r"d[ée]butants?|cadets?|self[\s-]*sponsored|type\s+rating\s+(?:course|training)\s+provided",
            re.IGNORECASE,
        ),
    ),
    ("Minimum 300 heures de vol", _heures_de_vol_accessibles),
    (
        "Anglais niveau 4",
        re.compile(
            r"(?:english|anglais)[^.;\n]{0,40}(?:level|niveau)\s*(?:4|5|6|iv)|"
            r"(?:icao|oaci)[^.;\n]{0,20}(?:level|niveau)\s*(?:4|5|6|iv)|"
            r"\belp\s*(?:level\s*)?[456]\b|language\s+proficiency|fcl\.?\s*055",
            re.IGNORECASE,
        ),
    ),
    (
        "Non type rated",
        re.compile(
            r"non[\s-]*type[\s-]*rated|un[\s-]*type[\s-]*rated|no\s+type[\s-]*rating|"
            r"type[\s-]*rating\s+(?:is\s+)?not\s+(?:required|needed)|without\s+(?:a\s+)?type[\s-]*rating|"
            r"sans\s+qualification\s+de\s+type|qt\s+non\s+requise",
            re.IGNORECASE,
        ),
    ),
    (
        "EASA ATPL",
        re.compile(
            r"easa[\s\-/]*(?:part[\s-]*fcl\s*)?atpl|atpl[^.;\n]{0,20}easa|"
            r"frozen\s*atpl|atpl\s*(?:gel[ée]e?|th[ée]orique)|atpl\s*\(\s*a\s*\)",
            re.IGNORECASE,
        ),
    ),
    (
        "First officer",
        re.compile(
            r"first[\s-]*officers?|second[\s-]*officers?|\bf\s*/\s*o\b|"
            r"officier\s+pilote\s+de\s+ligne|\bopl\b",
            re.IGNORECASE,
        ),
    ),
    (
        # Les aéroclubs annoncent « recherche FI saisonnier » sans jamais écrire
        # « pilote » : sans ce marqueur, ces postes — pourtant recherchés —
        # étaient tous écartés.
        "Instructeur / FI",
        re.compile(
            r"instructeur|instructrice|instructors?|flight\s+instructor|fluglehrer|"
            r"\bfi\s*\(?\s*[as]\s*\)?|\bfi\b(?=\s+(?:saisonnier|b[ée]n[ée]vole|planeur|avion|ulm))|"
            r"\bfe\b|\bfcl\.?\s*9\d\d|type\s+rating\s+instructor|\btri\b|\btre\b|\bsfi\b",
            re.IGNORECASE,
        ),
    ),
)


def criteres_presents(texte: str) -> list[str]:
    """Liste les critères requis effectivement présents dans le texte de l'annonce."""
    if not texte:
        return []
    trouves = []
    for libelle, test in CRITERES_REQUIS:
        satisfait = test(texte) if callable(test) else bool(test.search(texte))
        if satisfait:
            trouves.append(libelle)
    return trouves


def texte_annonce(annonce: dict) -> str:
    """Texte sur lequel les filtres travaillent : titres, extrait et adresse.

    L'adresse est incluse à dessein : sur les bourses d'emploi, l'intitulé exact
    du poste figure dans l'URL (« /jobs/first-officer-non-type-rated ») alors que
    l'extrait peut être vide.
    """
    champs = ("titre_fr", "titre_original", "extrait", "lien")
    return " ".join(str(annonce.get(c) or "") for c in champs)


def motif_exclusion(annonce: dict) -> str | None:
    """Renvoie le motif d'exclusion d'une annonce, ou None si elle est retenue."""
    if not est_offre_emploi(annonce.get("lien") or ""):
        return "actualite"
    texte = texte_annonce(annonce)
    if nationalite_bloquante(texte):
        return "nationalite"
    if not criteres_presents(texte):
        return "criteres"
    return None
