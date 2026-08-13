#!/usr/bin/env python3
"""Accès réseau et lecture de flux, partagés par le collecteur et le registre
des compagnies.

Ces fonctions vivaient dans ``collecte.py``. Elles ont été extraites quand
``compagnies.py`` a eu besoin des mêmes outils : les importer depuis
``collecte.py`` aurait créé un cycle, les recopier aurait fait diverger deux
versions du même code.
"""

from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; veille-emploi-pilote-perso/1.0)"}


def telecharger(url: str, timeout: int = 30) -> bytes:
    requete = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(requete, timeout=timeout) as reponse:
        return reponse.read()


def nettoyer_html(texte: str) -> str:
    texte = re.sub(r"<[^>]+>", " ", texte or "")
    texte = html.unescape(texte)
    return re.sub(r"\s+", " ", texte).strip()


def texte_visible(page: str, plafond: int = 40000) -> str:
    """Texte lisible d'une page HTML, débarrassé du code et de la navigation.

    Sert à examiner une annonce **en entier** et non le seul extrait de 400
    caractères conservé en base : une exigence linguistique est souvent enfouie
    au milieu d'une fiche de poste, sous « Profil recherché ».

    Les blocs de navigation, d'en-tête et de pied de page sont retirés : ils
    répètent sur toutes les fiches d'un site des mots qui fausseraient l'analyse
    (un sélecteur de langue « Deutsch / Español » en haut de page ferait croire
    à une exigence linguistique sur chaque annonce).
    """
    sans_code = re.sub(
        r"<(script|style|noscript|svg|head|nav|header|footer|form|select)\b[^>]*>.*?</\1>",
        " ",
        page or "",
        flags=re.DOTALL | re.IGNORECASE,
    )
    texte = re.sub(r"<[^>]+>", " ", sans_code)
    texte = html.unescape(texte)
    return re.sub(r"\s+", " ", texte).strip()[:plafond]


def telecharger_texte(url: str, timeout: int = 20) -> str:
    """Texte lisible d'une page distante ; chaîne vide si elle est inaccessible."""
    try:
        return texte_visible(telecharger(url, timeout).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 — une fiche illisible ne bloque pas les autres
        return ""


def date_iso(brut: str) -> str:
    """Normalise une date RFC 822 (flux RSS) en ISO 8601 UTC.

    Renvoie la chaîne d'origine si elle n'est pas analysable : mieux vaut une
    date approximative qu'une annonce écartée faute de date.
    """
    if not brut:
        return ""
    try:
        return parsedate_to_datetime(brut).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return brut


def lire_flux_rss(contenu: bytes) -> list[dict]:
    """Extrait les items d'un flux RSS (titre, lien, date, description)."""
    racine = ET.fromstring(contenu)
    items = []
    for item in racine.findall(".//item"):
        titre = nettoyer_html(item.findtext("title") or "")
        lien = (item.findtext("link") or "").strip()
        if not titre or not lien:
            continue
        items.append(
            {
                "titre": titre,
                "lien": lien,
                "date_publication": date_iso(item.findtext("pubDate") or ""),
                "extrait": nettoyer_html(item.findtext("description") or "")[:400],
                "media": nettoyer_html(item.findtext("source") or ""),
            }
        )
    return items
