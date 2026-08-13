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


# --- 3. Langue de travail autre que le français ou l'anglais ---------------
#
# Le candidat maîtrise le français et l'anglais, pas d'autre langue. Une
# annonce qui demande une troisième langue est écartée.
#
# Deux formulations bien différentes coexistent dans les annonces :
#
#   exigence : « fluent Arabic required », « Thai language mandatory »
#   atout    : « la maîtrise d'autres langues locales du pays d'emploi est un
#              atout », « German is a plus »
#
# Seules les exigences fermes écartent. Un simple bonus ne disqualifie
# personne : « Spanish ICAO Level Proficiency >= 4 would be a plus » sur un
# poste de copilote A330 à Madrid laisse le candidat parfaitement éligible,
# l'anglais niveau 4 suffisant à remplir les exigences. Écarter ces annonces
# faisait perdre des postes candidatables.
#
# Passer cet interrupteur à True écarte aussi les simples atouts.
ECARTER_SUR_LANGUE_ATOUT = False

# Version des motifs linguistiques. À incrémenter dès qu'ils changent : le
# collecteur relit alors les annonces analysées par une version antérieure.
# Sans ce numéro, une annonce examinée par une version qui ne savait pas encore
# lire l'allemand resterait marquée « aucune exigence » à jamais.
VERSION_ANALYSE_LANGUE = 2

# Langues que le candidat maîtrise : leur mention ne bloque jamais.
LANGUES_MAITRISEES = r"fran[çc]ais|french|anglais|english|british|american"

# Langues dont la mention, en contexte linguistique, écarte l'annonce.
# Écrites en français, en anglais et dans leur propre langue quand l'annonce
# d'origine n'est pas traduite.
LANGUES_ETRANGERES = (
    r"allemand|german|deutsch|espagnol|spanish|espa[ñn]ol|italien|italian|italiano|"
    r"portugais|portuguese|portugu[êe]s|n[ée]erlandais|dutch|nederlands|"
    r"russe|russian|русский|arabe|arabic|العربية|chinois|chinese|mandarin|cantonais|"
    r"cantonese|中文|普通话|japonais|japanese|日本語|cor[ée]en|korean|한국어|"
    r"tha[ïi]|thai|vietnamien|vietnamese|indon[ée]sien|indonesian|bahasa|"
    r"malais|malay|tagalog|filipino|hindi|ourdou|urdu|bengali|tamoul|tamil|"
    r"turc|turkish|t[üu]rk[çc]e|grec|greek|polonais|polish|polski|"
    r"tch[èe]que|czech|hongrois|hungarian|roumain|romanian|bulgare|bulgarian|"
    r"serbe|serbian|croate|croatian|slovaque|slovak|slov[èe]ne|slovenian|"
    r"ukrainien|ukrainian|su[ée]dois|swedish|norv[ée]gien|norwegian|"
    r"danois|danish|finnois|finnish|islandais|icelandic|"
    r"h[ée]breu|hebrew|persan|persian|farsi|kazakh|ouzbek|uzbek|mongol|mongolian|"
    r"khmer|lao|birman|burmese|n[ée]palais|nepali|cinghalais|sinhala|"
    r"swahili|amharique|amharic|afrikaans|malgache|malagasy|cr[ée]ole|creole|"
    r"tahitien|tahitian|reo m[āa]ohi|wallisien|dreh[uû]|nengone|paic[îi]"
)

# Mots qui signalent qu'on parle bien de compétence linguistique, et non d'une
# nationalité ou d'une destination : « Spanish airline » ne doit rien déclencher.
CONTEXTE_LANGUE = (
    r"langues?|language|linguistique|ma[îi]tris|parl[ée]?|speak|spoken|speaker|"
    r"fluent|courant|bilingue|bilingual|trilingue|proficien|niveau|level|"
    r"lu\s+[ée]crit|written|oral|communiquer|communicate|"
    # « La connaissance du tahitien est appréciée » : sans ces mots-là, la
    # formulation la plus courante en français passait au travers.
    r"connaissances?|knowledge|notions?|comprendre|understand|"
    # Une annonce qui exige une langue locale est souvent rédigée dans cette
    # langue : « Deutsch und Englisch in Wort und Schrift » n'était pas
    # détecté, faute d'un seul mot de contexte allemand.
    r"sprache|kenntnisse|flie[ßs]end|verhandlungssicher|wort\s+und\s+schrift|muttersprache|"
    r"idioma|nivel|dominio|conocimientos|hablado|"
    r"lingua|livello|conoscenz|"
    r"l[íi]ngua|n[íi]vel|conhecimentos|fluente|"
    r"taal|vloeiend|beheersing"
)

# Formulations qui font de la langue une exigence ferme.
EXIGENCE = (
    r"requis|required|require|mandatory|obligatoire|exig[ée]|essential|must|"
    r"n[ée]cessaire|necessary|imp[ée]ratif|indispensable|minimum|demand[ée]|"
    r"erforderlich|vorausgesetzt|zwingend|ben[öo]tigt|"
    r"requerido|obligatorio|imprescindible|richiesto|obrigat[óo]rio|vereist"
)

# Formulations qui n'en font qu'un avantage. Cette liste prime sur la
# précédente : « would be a plus » contient « plus », et c'est ce mot-là qui
# décide, même si la phrase parle par ailleurs d'exigences.
ATOUT = (
    r"atout|asset|plus|avantage|advantage|appr[ée]ci|souhait|desirable|preferred|bonus|"
    r"not\s+a\s+requirement|von\s+vorteil|w[üu]nschenswert|deseable|valorable|gradito|pluspunt"
)


def _fenetre(motif_a: str, motif_b: str, largeur: int = 70) -> re.Pattern[str]:
    """Motif : A puis B, ou B puis A, séparés d'au plus ``largeur`` caractères.

    Une compétence linguistique s'énonce dans les deux ordres — « fluent in
    Arabic » comme « Arabic (fluent) » — et le mot qualifiant peut précéder ou
    suivre. Chercher les deux sens évite d'en manquer la moitié.
    """
    return re.compile(
        rf"(?:{motif_a})[^.;\n]{{0,{largeur}}}?(?:{motif_b})"
        rf"|(?:{motif_b})[^.;\n]{{0,{largeur}}}?(?:{motif_a})",
        re.IGNORECASE,
    )


# Une langue étrangère nommée, dans un contexte de compétence linguistique.
LANGUE_ETRANGERE_CITEE = _fenetre(LANGUES_ETRANGERES, CONTEXTE_LANGUE)

# La formulation générique, qui ne nomme aucune langue mais en désigne une
# autre par construction : « autres langues locales du pays d'emploi ».
LANGUE_LOCALE = re.compile(
    r"(?:autres?\s+)?langues?\s+(?:locales?|du\s+pays|r[ée]gionales?|vernaculaires?)|"
    r"local\s+languages?|language\s+of\s+the\s+country|native\s+language|"
    r"langue\s+maternelle\s+(?!fran)",
    re.IGNORECASE,
)


def langue_bloquante(texte: str) -> tuple[str, str] | None:
    """Renvoie (extrait, nature) si l'annonce réclame une troisième langue.

    ``nature`` vaut « exigence » ou « atout ». Renvoie None si l'annonce ne
    demande que du français, de l'anglais, ou rien de particulier.
    """
    if not texte:
        return None

    trouve = LANGUE_ETRANGERE_CITEE.search(texte) or LANGUE_LOCALE.search(texte)
    if not trouve:
        return None

    extrait = trouve.group(0)
    # Une phrase peut citer plusieurs langues : « English and French required,
    # Spanish is a plus » ne doit pas être écartée sur son seul « English ».
    if re.fullmatch(rf"[^a-zA-Zà-üÀ-Ü]*(?:{LANGUES_MAITRISEES})[^a-zA-Zà-üÀ-Ü]*", extrait, re.IGNORECASE):
        return None

    # La nature se lit dans la phrase entière autour de la trouvaille, pas dans
    # le seul fragment : « atout » est souvent rejeté en fin de phrase.
    debut = max(0, trouve.start() - 120)
    phrase = texte[debut:trouve.end() + 120]
    if re.search(ATOUT, phrase, re.IGNORECASE):
        nature = "atout"
    else:
        # Sans qualificatif, c'est une exigence : « Flight Simulator Instructor
        # – Chinese Speaking » ne présente pas le chinois comme un bonus, il
        # définit le poste. Classer ces cas en « atout » les aurait laissés
        # passer dès que l'interrupteur ci-dessus serait désactivé.
        nature = "exigence"
    return extrait.strip(), nature


# --- 4. Critères requis : au moins un doit figurer dans l'annonce -----------
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


def langue_ecarte(verdict: tuple[str, str] | dict | None) -> bool:
    """Ce verdict linguistique justifie-t-il d'écarter l'annonce ?

    Accepte le tuple renvoyé par ``langue_bloquante`` comme le dictionnaire
    enregistré en base après lecture intégrale de l'annonce.
    """
    if not verdict:
        return False
    nature = verdict[1] if isinstance(verdict, tuple) else verdict.get("nature")
    return nature == "exigence" or ECARTER_SUR_LANGUE_ATOUT


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
    # Verdict issu de la lecture intégrale de l'annonce, quand elle a eu lieu :
    # il l'emporte, car il a vu la fiche entière là où le titre et l'extrait ne
    # montrent que la vitrine.
    if langue_ecarte(annonce.get("langue_exigee")):
        return "langue"
    if langue_ecarte(langue_bloquante(texte)):
        return "langue"
    if not criteres_presents(texte):
        return "criteres"
    return None
