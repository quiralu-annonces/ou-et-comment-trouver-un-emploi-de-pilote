#!/usr/bin/env python3
"""Générateur du site statique « Où et comment trouver un emploi de pilote ».

Lit la base ``data/annonces.json`` et produit ``docs/index.html``, page
autonome (aucune ressource externe) servie par GitHub Pages. Les décisions du
visiteur (pas intéressé / candidature envoyée / refus) sont mémorisées dans
son navigateur (localStorage) et survivent aux régénérations car les
identifiants d'annonces sont stables.

Usage : python collecteur/genere_site.py
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from filtres import motif_exclusion  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "data" / "annonces.json"
FICHIER_SITE = RACINE / "docs" / "index.html"
FICHIER_VISUEL = RACINE / "assets" / "cockpit.jpg"

MAX_ANNONCES_PAGE = 500  # la base complète reste dans data/annonces.json

# --- Règles d'affichage demandées ------------------------------------------
# Elles s'appliquent à la GÉNÉRATION, pas à la collecte : data/annonces.json
# continue d'historiser l'intégralité des annonces, rien n'est perdu. Seule la
# page publique est restreinte.

FENETRE_JOURS = 31  # n'afficher que les annonces parues depuis moins d'un mois

# Le collecteur range États-Unis, Canada et Mexique dans « Amérique du Nord ».
# Les États-Unis sont hors périmètre (pas d'autorisation de travail, pas de
# sponsorship), le Canada et le Québec restent couverts. On sépare donc les deux
# au moment de générer la page.
REGION_AMNORD = "Amérique du Nord"
REGION_CANADA = "Canada / Québec"

INDICES_CANADA = [
    "canada", "canadien", "canadian", "québec", "quebec", "montréal", "montreal",
    "air canada", "westjet", "porter airlines", "radio-canada", "toronto",
    "vancouver", "ottawa", "calgary", "winnipeg", "transat", "nolinor",
]

MODELE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Où et comment trouver un emploi de pilote d'avion — offres mondiales mises à jour chaque jour</title>
<meta name="description" content="Où et comment trouver un emploi de pilote de ligne, copilote, cadet ou instructeur : veille mondiale automatique des offres (Europe, Amérique, Asie, Moyen-Orient, Afrique, Océanie), traduites en français et mises à jour deux fois par jour.">
<meta property="og:title" content="Où et comment trouver un emploi de pilote d'avion">
<meta property="og:description" content="Veille mondiale automatique des offres d'emploi de pilote, traduites en français, mises à jour deux fois par jour.">
<meta property="og:type" content="website">
<style>
  :root {
    --bg: #0f1416;
    --panel: #1a2126;
    --panel-2: #212b31;
    --border: #2e3a41;
    --text: #e8edf0;
    --text-dim: #9fb0b8;
    --accent: #4fb3a9;
    --accent-2: #d9a441;
    --danger: #c26b5f;
    --success: #5f9e6e;
    --radius: 10px;
    --cockpit-w: clamp(320px, 36vw, 720px);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    padding: 20px;
    max-width: 980px;
    margin: 0 auto;
  }
  h1 { font-size: 22px; margin: 0 0 4px; text-wrap: balance; }
  .subtitle { color: var(--text-dim); font-size: 13px; margin-bottom: 18px; line-height: 1.5; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; align-items: center; }
  .toolbar-label {
    font-size: 12px; color: #ffd429; font-weight: 800; text-transform: uppercase;
    letter-spacing: .06em; margin-right: 4px; min-width: 152px;
  }
  .toolbar button {
    background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
    border-radius: 20px; padding: 6px 14px; font-size: 13px; cursor: pointer;
  }
  .toolbar button.active { background: var(--accent); color: #0f1416; border-color: var(--accent); font-weight: 600; }
  .searchbar { margin-bottom: 12px; }
  .searchbar input {
    width: 100%; background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 10px 14px; font-size: 14px;
  }
  .searchbar input:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
  .count-badge {
    background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 10px 14px; font-size: 13px; color: var(--text-dim); margin-bottom: 16px; line-height: 1.6;
  }
  .count-badge strong { color: var(--text); }
  .note { font-size: 12px; color: var(--text-dim); margin-top: 6px; font-style: italic; }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 16px 18px; margin-bottom: 14px; transition: opacity .2s;
  }
  .card.dismissed { opacity: 0.45; }
  .card-title { font-size: 16px; font-weight: 700; margin-bottom: 4px; text-wrap: balance; }
  .card-original { color: var(--text-dim); font-size: 12px; font-style: italic; margin-bottom: 6px; }
  .card-sub { color: var(--text-dim); font-size: 13px; margin-bottom: 10px; }
  .card-extrait { font-size: 13px; line-height: 1.5; color: var(--text); margin-bottom: 10px; }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
  .tag {
    font-size: 11px; padding: 3px 9px; border-radius: 20px; border: 1px solid var(--border);
    color: var(--text-dim);
  }
  .tag.status-Nouvelle { color: var(--accent); border-color: var(--accent); }
  .tag.status-Ecartee { color: var(--danger); border-color: var(--danger); }
  .tag.status-Postule { color: var(--success); border-color: var(--success); }
  .tag.status-Refus { color: var(--danger); border-color: var(--danger); }
  .table-wrap { overflow-x: auto; }
  table.details { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 12px; }
  table.details td { padding: 4px 8px 4px 0; vertical-align: top; border-top: 1px solid var(--border); }
  table.details td.label { color: var(--text-dim); width: 190px; white-space: nowrap; }
  .actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .actions a, .actions button {
    font-size: 13px; border-radius: 6px; padding: 7px 12px; border: 1px solid var(--border);
    background: var(--panel-2); color: var(--text); cursor: pointer; text-decoration: none;
  }
  .actions a.primary { background: var(--accent); color: #0f1416; border-color: var(--accent); font-weight: 600; }
  .actions button.dismiss { color: var(--danger); border-color: var(--danger); }
  .actions button.applied { color: var(--success); border-color: var(--success); }
  .actions button.refused { color: var(--danger); border-color: var(--danger); }
  .actions button.undo { color: var(--text-dim); }
  .empty { color: var(--text-dim); text-align: center; padding: 40px 0; font-size: 14px; }
  footer { color: var(--text-dim); font-size: 12px; margin: 30px 0 10px; text-align: center; line-height: 1.6; }

  /* Visuel cockpit : panneau fixe à droite, il ne défile pas avec les annonces.
     Le masque en dégradé estompe ses bords pour qu'il se fonde dans le fond
     sombre au lieu de former un rectangle collé sur la page. */
  .cockpit {
    display: none;
    position: fixed;
    top: 50%; right: 0;
    transform: translateY(-50%);
    width: var(--cockpit-w);
    aspect-ratio: 734 / 446;
    background-image: url("__COCKPIT__");
    background-size: cover;
    background-position: center;
    /* Fondu volontairement tardif : le cœur de l'image reste pleinement opaque,
       seuls les bords s'estompent pour éviter l'effet de rectangle collé. */
    -webkit-mask-image: radial-gradient(ellipse 82% 78% at 55% 50%,
              #000 0%, #000 52%, rgba(0,0,0,.75) 72%, rgba(0,0,0,.3) 88%, transparent 100%);
            mask-image: radial-gradient(ellipse 82% 78% at 55% 50%,
              #000 0%, #000 52%, rgba(0,0,0,.75) 72%, rgba(0,0,0,.3) 88%, transparent 100%);
    -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
    -webkit-mask-size: 100% 100%;   mask-size: 100% 100%;
    pointer-events: none;
  }
  /* Le visuel n'apparaît que si l'écran est assez large pour l'accueillir sans
     empiéter sur la colonne de lecture.
     margin-left: 0 est indispensable : sans lui, le « margin: 0 auto » du body
     absorberait tout l'espace libre à gauche et repousserait les annonces vers
     la droite, contre l'image. Ici elles restent collées au bord gauche. */
  @media (min-width: 1500px) {
    .cockpit { display: block; }
    body { margin-left: 0; margin-right: calc(var(--cockpit-w) + 48px); }
  }
</style>
</head>
<body>

<div class="cockpit" aria-hidden="true"></div>

<h1>✈️ Où et comment trouver un emploi de pilote d'avion</h1>
<div class="subtitle">
Veille mondiale automatique des offres d'emploi de pilote de ligne, copilote, cadet et instructeur —
Europe, Canada / Québec, Amérique du Sud, Asie, Moyen-Orient, Afrique, Océanie.
Les annonces étrangères sont traduites en français. Vos décisions (pas intéressé / candidature envoyée / refus)
sont mémorisées sur cet appareil : une annonce traitée ne réapparaît plus dans « Nouvelles ».<br>
Seules les annonces parues <strong>depuis moins d'un mois</strong> sont affichées. Les offres situées
aux <strong>États-Unis</strong> ne sont pas retenues.<br>
<strong>Dernière mise à jour de la base : __DATE_MAJ__</strong>
</div>

<div id="toolbar" class="toolbar"></div>
<div class="searchbar"><input id="search" type="search" placeholder="Rechercher (compagnie, appareil, pays…)" aria-label="Rechercher dans les annonces"></div>
<div id="countBadge" class="count-badge"></div>
<div id="list"></div>

<footer>
Page générée automatiquement deux fois par jour par un collecteur open source (flux publics gratuits : Google News multilingue, SNPI…).<br>
__NB_AFFICHEES__ annonce(s) affichée(s) : parues depuis moins d'un mois, hors États-Unis.<br>
Base historisée : aucune annonce n'est supprimée — __NB__ annonces collectées à ce jour, consultables dans <code>data/annonces.json</code>.
</footer>

<script>
const ANNONCES = __DATA__;

const REGIONS = ["Toutes", "Europe", "Canada / Québec", "Amérique du Sud", "Asie", "Moyen-Orient", "Océanie", "Afrique", "Monde"];
const STATUSES = {
  "Nouvelle": { label: "Nouvelles", cls: "status-Nouvelle" },
  "Ecartee": { label: "Écartées", cls: "status-Ecartee" },
  "Postule": { label: "Candidature envoyée", cls: "status-Postule" },
  "Refus": { label: "Refus reçu", cls: "status-Refus" },
};

const CLE = "veille-pilote:status:";
let statusMap = {};
let currentRegionFilter = "Toutes";
let currentStatusFilter = "Nouvelle";
let searchTerm = "";

function loadStatuses() {
  statusMap = {};
  for (const a of ANNONCES) {
    statusMap[a.id] = localStorage.getItem(CLE + a.id) || "Nouvelle";
  }
}

function setStatus(id, status) {
  statusMap[id] = status;
  try { localStorage.setItem(CLE + id, status); } catch (e) { console.error(e); }
  render();
}

function echap(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function dateCourte(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

function mkBtn(texte, actif, onclick) {
  const b = document.createElement("button");
  b.textContent = texte;
  if (actif) b.classList.add("active");
  if (onclick) b.onclick = onclick;
  return b;
}

/* Chaque famille de filtres occupe sa propre ligne, précédée de son intitulé :
   on lit d'un coup d'œil sur quel critère on agit. */
function mkRow(intitule) {
  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;align-items:center;width:100%";
  const l = document.createElement("span");
  l.className = "toolbar-label";
  l.textContent = intitule;
  row.appendChild(l);
  return row;
}

function renderToolbar() {
  const tb = document.getElementById("toolbar");
  tb.innerHTML = "";

  /* Une seule tranche d'ancienneté est publiée : le bouton indique la règle
     appliquée, il n'y a pas d'autre choix à proposer. */
  const rowDate = mkRow("Date de diffusion");
  rowDate.appendChild(mkBtn(`< 1 mois (${ANNONCES.length})`, true, null));
  tb.appendChild(rowDate);

  const rowRegion = mkRow("Région");
  REGIONS.forEach(r => rowRegion.appendChild(
    mkBtn(r, r === currentRegionFilter, () => { currentRegionFilter = r; render(); })));
  tb.appendChild(rowRegion);

  const rowStatus = mkRow("Mon statut");
  rowStatus.appendChild(
    mkBtn("Toutes", currentStatusFilter === "Toutes", () => { currentStatusFilter = "Toutes"; render(); }));
  Object.entries(STATUSES).forEach(([key, meta]) => rowStatus.appendChild(
    mkBtn(meta.label, key === currentStatusFilter, () => { currentStatusFilter = key; render(); })));
  tb.appendChild(rowStatus);
}

function renderCard(a) {
  const status = statusMap[a.id] || "Nouvelle";
  const dismissedCls = status !== "Nouvelle" ? "dismissed" : "";
  const statusMeta = STATUSES[status] || STATUSES["Nouvelle"];
  const original = (a.titre_original && a.titre_original !== a.titre_fr)
    ? `<div class="card-original">Titre original : ${echap(a.titre_original)}</div>` : "";
  const extrait = a.extrait ? `<div class="card-extrait">${echap(a.extrait)}</div>` : "";
  let details = "";
  if (a.details) {
    const lignes = Object.entries(a.details)
      .map(([k, v]) => `<tr><td class="label">${echap(k)}</td><td>${echap(v)}</td></tr>`).join("");
    details = `<div class="table-wrap"><table class="details">${lignes}</table></div>`;
  }
  const datePub = a.date_publication ? ` — publiée le ${dateCourte(a.date_publication)}` : "";
  return `
  <div class="card ${dismissedCls}">
    <div class="card-title">${echap(a.titre_fr)}</div>
    ${original}
    <div class="card-sub">${echap(a.source)}${datePub} — repérée le ${dateCourte(a.premiere_collecte)}</div>
    <div class="tags">
      <span class="tag">${echap(a.region)}</span>
      <span class="tag">${echap((a.langue || "").toUpperCase())}</span>
      <span class="tag ${statusMeta.cls}">${statusMeta.label === "Nouvelles" ? "Nouvelle" : statusMeta.label}</span>
    </div>
    ${extrait}
    ${details}
    <div class="actions">
      <a class="primary" href="${echap(a.lien)}" target="_blank" rel="noopener">Ouvrir l'annonce ↗</a>
      ${status === "Nouvelle" ? `
        <button class="dismiss" onclick="setStatus('${a.id}','Ecartee')">Pas intéressé</button>
        <button class="applied" onclick="setStatus('${a.id}','Postule')">Candidature envoyée</button>
      ` : `
        ${status === "Postule" ? `<button class="refused" onclick="setStatus('${a.id}','Refus')">Marquer refus reçu</button>` : ""}
        <button class="undo" onclick="setStatus('${a.id}','Nouvelle')">↺ Revenir à "Nouvelle"</button>
      `}
    </div>
  </div>`;
}

function render() {
  renderToolbar();
  const list = document.getElementById("list");
  const badge = document.getElementById("countBadge");

  let items = ANNONCES.filter(a => currentRegionFilter === "Toutes" || a.region === currentRegionFilter);
  if (currentStatusFilter !== "Toutes") {
    items = items.filter(a => (statusMap[a.id] || "Nouvelle") === currentStatusFilter);
  }
  if (searchTerm) {
    const t = searchTerm.toLowerCase();
    items = items.filter(a =>
      (a.titre_fr || "").toLowerCase().includes(t) ||
      (a.titre_original || "").toLowerCase().includes(t) ||
      (a.extrait || "").toLowerCase().includes(t) ||
      (a.source || "").toLowerCase().includes(t));
  }

  /* Une annonce déjà traitée disparaît du filtre « Nouvelles ». Sans explication,
     l'écart entre le total publié et le nombre affiché est incompréhensible :
     on le dit, et on indique comment revoir les annonces masquées. */
  const traitees = ANNONCES.filter(a => (statusMap[a.id] || "Nouvelle") !== "Nouvelle").length;
  badge.innerHTML =
    `<strong>${items.length}</strong> annonce(s) affichée(s) · ` +
    `<strong>${ANNONCES.length}</strong> retenue(s) au total — parues depuis moins d'un mois, hors États-Unis.` +
    (traitees > 0 && currentStatusFilter === "Nouvelle"
      ? `<div class="note">${traitees} annonce(s) que vous avez déjà traitée(s) sont masquées par le filtre « Nouvelles ». Cliquez « Toutes » dans la ligne « Mon statut » pour les revoir.</div>`
      : "");

  list.innerHTML = items.length
    ? items.map(renderCard).join("")
    : `<div class="empty">Aucune annonce dans cette catégorie.</div>`;
}

document.getElementById("search").addEventListener("input", (e) => {
  searchTerm = e.target.value.trim();
  render();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") { loadStatuses(); render(); }
});
window.addEventListener("pageshow", (e) => { if (e.persisted) { loadStatuses(); render(); } });

loadStatuses();
render();
</script>
</body>
</html>
"""


def _texte_annonce(annonce: dict) -> str:
    """Concatène les champs où un indice de pays peut apparaître."""
    champs = ("titre_fr", "titre_original", "extrait", "source", "lien")
    return " ".join(str(annonce.get(c) or "") for c in champs).lower()


def _date_reference(annonce: dict) -> datetime | None:
    """Date servant à juger l'ancienneté : publication si connue, sinon collecte."""
    for cle in ("date_publication", "premiere_collecte"):
        brut = annonce.get(cle)
        if not brut:
            continue
        try:
            return datetime.fromisoformat(brut).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def appliquer_regles(annonces: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Applique les deux règles d'affichage et reclasse le Canada.

    Renvoie les annonces retenues et un compte-rendu chiffré des exclusions,
    pour que la restriction ne soit jamais silencieuse.
    """
    limite = datetime.now(timezone.utc) - timedelta(days=FENETRE_JOURS)
    retenues: list[dict] = []
    stats = {
        "actualites": 0, "nationalite": 0,
        "trop_anciennes": 0, "sans_date": 0, "etats_unis": 0, "canada": 0,
    }

    for annonce in annonces:
        # Le tri le plus important d'abord : ce n'est une annonce que si c'est
        # une offre d'emploi. Les articles de presse n'ont rien à faire ici.
        motif = motif_exclusion(annonce)
        if motif == "actualite":
            stats["actualites"] += 1
            continue
        if motif == "nationalite":
            stats["nationalite"] += 1
            continue

        date_ref = _date_reference(annonce)
        if date_ref is None:
            # Sans date exploitable, impossible d'affirmer que l'annonce est
            # récente : on l'écarte plutôt que de la présenter comme telle.
            stats["sans_date"] += 1
            continue
        if date_ref < limite:
            stats["trop_anciennes"] += 1
            continue

        if annonce.get("region") == REGION_AMNORD:
            if any(indice in _texte_annonce(annonce) for indice in INDICES_CANADA):
                annonce = {**annonce, "region": REGION_CANADA}
                stats["canada"] += 1
            else:
                # Dans cette région, tout ce qui n'est pas identifié comme
                # canadien relève des États-Unis : hors périmètre.
                stats["etats_unis"] += 1
                continue

        retenues.append(annonce)

    return retenues, stats


def generer() -> None:
    base = json.loads(FICHIER_DONNEES.read_text(encoding="utf-8"))
    annonces = base["annonces"]

    retenues, stats = appliquer_regles(annonces)

    # Les plus récentes d'abord (date de collecte puis date de publication).
    annonces_triees = sorted(
        retenues,
        key=lambda a: (a.get("premiere_collecte") or "", a.get("date_publication") or ""),
        reverse=True,
    )[:MAX_ANNONCES_PAGE]

    date_maj = base.get("derniere_collecte")
    if date_maj:
        try:
            dt = datetime.fromisoformat(date_maj)
            date_maj = dt.astimezone(timezone.utc).strftime("%d/%m/%Y à %H:%M UTC")
        except ValueError:
            pass
    else:
        date_maj = "initialisation en cours"

    # Le visuel est intégré en base64 : la page reste autonome, sans requête
    # externe ni fichier image à servir à côté.
    if FICHIER_VISUEL.is_file():
        octets = FICHIER_VISUEL.read_bytes()
        cockpit = "data:image/jpeg;base64," + base64.b64encode(octets).decode("ascii")
    else:
        # Sans le visuel, la page reste parfaitement fonctionnelle.
        print(f"Visuel absent ({FICHIER_VISUEL}) : page générée sans illustration.")
        cockpit = ""

    page = (
        MODELE
        .replace("__DATA__", json.dumps(annonces_triees, ensure_ascii=False))
        .replace("__DATE_MAJ__", date_maj)
        .replace("__NB_AFFICHEES__", str(len(annonces_triees)))
        .replace("__NB__", str(len(annonces)))
        .replace("__COCKPIT__", cockpit)
    )
    FICHIER_SITE.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_SITE.write_text(page, encoding="utf-8")
    print(
        f"Site généré : {FICHIER_SITE}\n"
        f"  {len(annonces_triees)} offre(s) affichée(s) sur {len(annonces)} entrées en base\n"
        f"  écartées : {stats['actualites']} actualités (pas des offres), "
        f"{stats['nationalite']} nationalité exigée non détenue,\n"
        f"             {stats['trop_anciennes']} de plus de {FENETRE_JOURS} jours, "
        f"{stats['etats_unis']} aux États-Unis, {stats['sans_date']} sans date exploitable\n"
        f"  reclassées « {REGION_CANADA} » : {stats['canada']}"
    )


if __name__ == "__main__":
    generer()
