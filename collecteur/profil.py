#!/usr/bin/env python3
"""Profil du candidat, et confrontation des annonces à ce profil.

Jusqu'ici la sélection reposait sur des mots-clés génériques. Le curriculum
vitæ fournit des chiffres : 290 heures de vol, anglais niveau 4, aucune
qualification de type. Une annonce exigeant 1500 heures ou un anglais niveau 5
n'est pas « moins intéressante », elle est **hors d'atteinte** — et l'afficher
fait perdre du temps à chaque consultation.

**Le piège de ce dossier est la double compétence.** Le candidat a dix ans de
maintenance aéronautique — Part-66 B1, CAT A, Falcon, Bombardier, A320 — et
cherche un poste de **pilote**. Les annonces de mécanicien lui correspondent
parfaitement sur le papier et ne l'intéressent pas. Un poste mixte
pilote-mécanicien, en revanche, lui convient. La règle est donc : écarter ce
qui est *uniquement* de la maintenance, jamais ce qui comporte du pilotage.

Les seuils sont ici, en un seul endroit, pour qu'ils suivent l'évolution du
candidat : ses heures augmenteront, son anglais peut passer au niveau 5, une
qualification de type peut s'ajouter.
"""

from __future__ import annotations

# --- Le candidat ------------------------------------------------------------

HEURES_TOTALES = 290
HEURES_PIC = 144

# Niveau OACI par langue. Une annonce qui exige davantage est hors d'atteinte.
LANGUES = {"francais": 6, "anglais": 4}

LICENCES = ("EASA ATPL", "CPL", "IR", "EASA")          # ATPL théorique, CPL/MEP, ME/IR
CERTIFICATS = ("classe 1", "MCC", "UPRT")
QUALIFICATIONS_TYPE: tuple[str, ...] = ()               # aucune à ce jour

# --- Seuils de mise à l'écart ----------------------------------------------

# Plancher d'heures au-delà duquel l'annonce est inatteignable. On compare au
# **minimum** exigé par l'annonce, jamais au maximum : une fiche qui propose un
# poste de copilote à 250 h et un poste de commandant à 3000 h reste ouverte.
# La marge sur les 290 heures détenues laisse la place aux arrondis et aux
# heures que le candidat continue d'accumuler.
SEUIL_HEURES_HORS_PORTEE = 500

# Entre les heures détenues et ce seuil, l'annonce est affichée mais signalée :
# elle est proche, sans être acquise.
SEUIL_HEURES_LIMITE = HEURES_TOTALES


def motif_profil(annonce: dict) -> str | None:
    """Motif d'incompatibilité entre l'annonce et le profil, ou None.

    Ne s'appuie que sur les mesures extraites de la fiche complète. Une annonce
    non encore lue en entier ne porte pas de mesures : elle n'est pas écartée,
    faute de preuve. Mieux vaut une annonce de trop qu'une annonce perdue sur
    une supposition.
    """
    mesures = annonce.get("exigences") or {}

    # Maintenance seule : le cœur de la consigne. La présence d'un mot de
    # pilotage suffit à conserver l'annonce, poste mixte compris.
    if mesures.get("maintenance") and not mesures.get("pilotage"):
        return "maintenance"

    # Langue exigée au-dessus du niveau détenu.
    for langue, niveau in (mesures.get("langues_exigees") or {}).items():
        if niveau > LANGUES.get(langue, 0):
            return "niveau_langue"

    # Plancher d'heures inatteignable.
    minimum = mesures.get("heures_min_exigees")
    if minimum and minimum > SEUIL_HEURES_HORS_PORTEE:
        return "heures"

    return None


def ecarts(annonce: dict) -> list[str]:
    """Écarts notables entre l'annonce et le profil, à afficher sur la fiche.

    Ne sert qu'à informer : ces mentions n'écartent rien. Elles disent au
    lecteur ce qui lui manque avant qu'il n'ouvre l'annonce.
    """
    mesures = annonce.get("exigences") or {}
    notes = []

    minimum = mesures.get("heures_min_exigees")
    if minimum and SEUIL_HEURES_LIMITE < minimum <= SEUIL_HEURES_HORS_PORTEE:
        notes.append(f"{minimum} h exigées, vous en avez {HEURES_TOTALES}")

    if mesures.get("type_rating_exige") and not QUALIFICATIONS_TYPE:
        notes.append("qualification de type à détenir, vous n'en avez aucune")

    if mesures.get("maintenance") and mesures.get("pilotage"):
        notes.append("poste mixte pilotage et maintenance")

    return notes


def atouts(annonce: dict) -> list[str]:
    """Points du profil que l'annonce réclame et que le candidat détient."""
    detenus = []
    for critere in annonce.get("criteres") or []:
        corps = critere.split("|", 1)[0]
        famille, _, valeur = corps.partition(":")
        if famille == "licence" and valeur in LICENCES:
            detenus.append(valeur)
        elif famille == "certificat" and valeur in CERTIFICATS:
            detenus.append(valeur)
        elif famille == "qualification" and valeur == "de type non requise":
            detenus.append("sans qualification de type")
    return detenus
