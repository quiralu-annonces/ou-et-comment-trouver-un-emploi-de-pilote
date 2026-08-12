#!/usr/bin/env python3
"""Registre des compagnies à interroger à chaque collecte.

Dix-huit compagnies françaises, ultramarines et d'aviation d'affaires sont
suivies nommément. Toutes n'exposent pas leurs offres de la même façon, et
c'est le point important de ce module : **chacune est classée selon ce qu'on
peut réellement en tirer**, plutôt que de faire croire à une couverture
automatique complète.

Quatre modes de collecte automatique :

``rss``       flux RSS d'un ATS (Teamtailor…) — le cas idéal.
``liste``     page HTML listant les offres, chaque offre ayant son lien propre.
``sitemap``   plan de site dédié aux offres (Air Calédonie publie le sien).
``recruitee`` API JSON publique des sites carrières Recruitee.

Et un mode sans collecte automatique :

``manuel``    page carrières rendue en JavaScript, protégée (HTTP 403) ou
              n'offrant qu'une adresse de candidature. Rien n'est moissonnable :
              ces compagnies sont publiées sur le site comme **liste à
              consulter à la main**, avec le lien et l'adresse de candidature.
              Les taire reviendrait à laisser croire qu'elles sont couvertes.

Le classement a été établi en sondant chaque site le 12 août 2026. Une
compagnie qui ouvrirait un vrai portail d'offres peut passer en mode
automatique sans autre changement que sa ligne dans ce fichier.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from reseau import lire_flux_rss, nettoyer_html, telecharger

# Chaque entrée : nom, région (au sens du site), page publique destinée à
# l'utilisateur, mode de collecte, et selon le mode : source technique,
# motif des liens d'offre, adresse de candidature.
COMPAGNIES: tuple[dict, ...] = (
    # --- Long-courrier et régulier métropole --------------------------------
    {
        "nom": "French bee",
        "region": "Europe",
        "page": "https://www.frenchbee.com/fr",
        "mode": "manuel",
        "contact": "cockpitrecruitement@frenchbee.com",
        "note": "Site protégé (HTTP 403) : candidature pilote par courriel.",
    },
    {
        "nom": "Corsair",
        "region": "Europe",
        "page": "https://www.flycorsair.com/en/information/corsair/recruitment",
        "mode": "manuel",
        "contact": "recrutementpilotecorsair@corsair.fr",
        "note": "Page carrières rendue en JavaScript : aucune offre lisible par un robot.",
    },
    {
        "nom": "La Compagnie",
        "region": "Europe",
        "page": "https://careers.werecruit.io/fr/la-compagnie",
        "mode": "liste",
        "source": "https://careers.werecruit.io/fr/la-compagnie",
        "motif_lien": r"/fr/la-compagnie/offres/[a-z0-9-]+",
    },
    {
        "nom": "Air Corsica",
        "region": "Europe",
        "page": "https://www.aircorsica.com/aircorsica-recrute",
        "mode": "manuel",
        "contact": "recrutement@aircorsica.com",
        "note": "Page unique sans offre individuelle : candidature par courriel.",
    },
    {
        "nom": "Amelia (Regourd Aviation)",
        "region": "Europe",
        "page": "https://career.flyamelia.com/",
        "mode": "recruitee",
        "source": "https://career.flyamelia.com/api/offers/",
    },
    {
        "nom": "Finist'air",
        "region": "Europe",
        "page": "https://www.finistair.fr/",
        "mode": "manuel",
        "note": "Compagnie de 7 salariés, sans page carrières : contact direct.",
    },
    # --- Outre-mer ----------------------------------------------------------
    {
        "nom": "Air Caraïbes",
        "region": "Amérique du Sud",
        "page": "https://recrutement.aircaraibes.com/",
        "mode": "manuel",
        "note": "Portail de recrutement rendu en JavaScript, liste d'offres inaccessible au robot.",
    },
    {
        "nom": "Air Austral",
        "region": "Afrique",
        "page": "https://www.air-austral.com/a-propos-dair-austral/recrutement.html",
        "mode": "manuel",
        "note": "Site protégé (HTTP 403) : consulter la page recrutement à la main.",
    },
    {
        "nom": "Aircalin",
        "region": "Océanie",
        "page": "https://carrieres.aircalin.com/offre-de-emploi/liste-offres.aspx?LCID=1036",
        "mode": "liste",
        "source": "https://carrieres.aircalin.com/offre-de-emploi/liste-offres.aspx?LCID=1036",
        "motif_lien": r"/offre-de-emploi/emploi-[a-z0-9\-]+_\d+\.aspx",
    },
    {
        "nom": "Air Calédonie",
        "region": "Océanie",
        "page": "https://www.air-caledonie.nc/",
        "mode": "sitemap",
        "source": "https://www.air-caledonie.nc/recrutements-sitemap.xml",
        "motif_lien": r"/recrutements/",
    },
    {
        "nom": "Air Tahiti Nui",
        "region": "Océanie",
        "page": "https://us.airtahitinui.com/careers",
        "mode": "manuel",
        "note": "Page carrières rendue en JavaScript.",
    },
    {
        "nom": "Groupe Air Tahiti",
        "region": "Océanie",
        "page": "https://carrieres.airtahiti.com/jobs",
        "mode": "rss",
        "source": "https://carrieres.airtahiti.com/jobs.rss",
    },
    {
        "nom": "Air Moana",
        "region": "Océanie",
        "page": "https://fr.airmoana.com/fr",
        "mode": "manuel",
        "note": "Aucune page carrières publique repérée.",
    },
    {
        "nom": "Air Saint-Pierre",
        "region": "Amérique du Nord",
        "page": "https://www.airsaintpierre.com/",
        "mode": "manuel",
        "contact": "vdrake@airsaintpierre.com",
        "note": "Offres publiées sur la page Facebook de la compagnie, pas sur son site.",
    },
    {
        "nom": "Air Loyauté",
        "region": "Océanie",
        "page": "https://www.air-loyaute.nc/",
        "mode": "manuel",
        "contact": "rh@air-loyaute.nc",
        "note": "Pas de section recrutement sur le site : candidature par courriel.",
    },
    # --- Aviation d'affaires ------------------------------------------------
    {
        "nom": "VallJet",
        "region": "Europe",
        "page": "https://www.valljet.com/les-offres/",
        "mode": "manuel",
        "note": "Liste d'offres rendue en JavaScript.",
    },
    {
        "nom": "Astonjet",
        "region": "Europe",
        "page": "https://astonjet.com/",
        "mode": "manuel",
        "note": "Aucune section recrutement dans le plan du site.",
    },
    {
        "nom": "IXair",
        "region": "Europe",
        "page": "https://ixair.com/",
        "mode": "manuel",
        "note": "Aucune section recrutement dans le plan du site.",
    },
    {
        "nom": "Pan Européenne",
        "region": "Europe",
        "page": "https://pan-europeenne.com/",
        "mode": "manuel",
        "contact": "peas.jobs@gmail.com",
        "note": "Offres diffusées par réseaux sociaux : candidature par courriel.",
    },
)

MODES_AUTOMATIQUES = ("rss", "liste", "sitemap", "recruitee")


def _titre_depuis_url(lien: str) -> str:
    """Reconstitue un intitulé lisible à partir du dernier segment d'une URL.

    Filet de sécurité quand le texte du lien est vide ou illisible :
    « emploi-officiers-pilotes-de-ligne-a330-h-f_59.aspx » devient
    « Officiers pilotes de ligne a330 h f ».
    """
    segment = lien.rstrip("/").rsplit("/", 1)[-1]
    segment = re.sub(r"\.(?:aspx?|html?|php)$", "", segment, flags=re.IGNORECASE)
    segment = re.sub(r"^(?:emploi|offre|job)s?[-_]", "", segment, flags=re.IGNORECASE)
    segment = re.sub(r"[-_]\d+$", "", segment)          # identifiant technique final
    segment = re.sub(r"^\d+[-_]", "", segment)          # identifiant technique initial
    segment = re.sub(r"[-_]+", " ", segment).strip()
    return segment[:1].upper() + segment[1:] if segment else ""


def _offres_rss(compagnie: dict) -> list[dict]:
    return lire_flux_rss(telecharger(compagnie["source"]))


def _offres_liste(compagnie: dict) -> list[dict]:
    """Lit une page HTML qui liste les offres, une offre = un lien.

    Le texte du lien porte l'intitulé du poste ; à défaut on le reconstitue
    depuis l'URL, qui le contient presque toujours.
    """
    page = telecharger(compagnie["source"]).decode("utf-8", "replace")
    motif = re.compile(
        r'<a\b[^>]*?href="(' + compagnie["motif_lien"] + r')"[^>]*?>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    items: list[dict] = []
    vus: set[str] = set()
    for chemin, texte in motif.findall(page):
        lien = urljoin(compagnie["source"], chemin)
        if lien in vus:
            continue
        vus.add(lien)
        titre = nettoyer_html(texte) or _titre_depuis_url(lien)
        if not titre:
            continue
        items.append(
            {"titre": titre, "lien": lien, "date_publication": "", "extrait": "", "media": ""}
        )
    return items


def _offres_sitemap(compagnie: dict) -> list[dict]:
    """Lit un plan de site dédié aux offres : une URL = une offre."""
    plan = telecharger(compagnie["source"]).decode("utf-8", "replace")
    motif = re.compile(r"<url>\s*<loc>(.*?)</loc>(?:\s*<lastmod>(.*?)</lastmod>)?", re.DOTALL)
    items = []
    for lien, modifie in motif.findall(plan):
        lien = lien.strip()
        if compagnie["motif_lien"] not in lien:
            continue
        titre = _titre_depuis_url(lien)
        if not titre:
            continue
        items.append(
            {
                "titre": titre,
                "lien": lien,
                "date_publication": (modifie or "").strip(),
                "extrait": "",
                "media": "",
            }
        )
    return items


def _offres_recruitee(compagnie: dict) -> list[dict]:
    """Lit l'API publique d'un site carrières Recruitee (JSON).

    Les champs varient selon la configuration du compte : on lit ce qui est
    présent et on se rabat sur les alternatives connues, plutôt que d'échouer
    sur une clé absente.
    """
    donnees = json.loads(telecharger(compagnie["source"]).decode("utf-8", "replace"))
    items = []
    for offre in donnees.get("offers", []):
        titre = (offre.get("title") or "").strip()
        lien = offre.get("careers_url") or offre.get("careers_apply_url") or ""
        if not titre or not lien:
            continue
        lieu = ", ".join(x for x in (offre.get("city"), offre.get("country")) if x)
        items.append(
            {
                "titre": f"{titre} — {lieu}" if lieu else titre,
                "lien": lien,
                "date_publication": offre.get("published_at") or offre.get("created_at") or "",
                "extrait": nettoyer_html(offre.get("description") or "")[:400],
                "media": "",
            }
        )
    return items


_LECTEURS = {
    "rss": _offres_rss,
    "liste": _offres_liste,
    "sitemap": _offres_sitemap,
    "recruitee": _offres_recruitee,
}


def offres_compagnie(compagnie: dict) -> list[dict]:
    """Offres publiées par une compagnie ; liste vide si mode manuel."""
    lecteur = _LECTEURS.get(compagnie["mode"])
    return lecteur(compagnie) if lecteur else []


def compagnies_automatiques() -> list[dict]:
    return [c for c in COMPAGNIES if c["mode"] in MODES_AUTOMATIQUES]


def compagnies_manuelles() -> list[dict]:
    return [c for c in COMPAGNIES if c["mode"] == "manuel"]
