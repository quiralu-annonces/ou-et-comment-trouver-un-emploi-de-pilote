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

import json
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "data" / "annonces.json"
FICHIER_SITE = RACINE / "docs" / "index.html"

MAX_ANNONCES_PAGE = 500  # la base complète reste dans data/annonces.json

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
  .toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
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
    padding: 10px 14px; font-size: 13px; color: var(--text-dim); margin-bottom: 16px;
  }
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
</style>
</head>
<body>

<h1>✈️ Où et comment trouver un emploi de pilote d'avion</h1>
<div class="subtitle">
Veille mondiale automatique des offres d'emploi de pilote de ligne, copilote, cadet et instructeur —
Europe, Amérique du Nord et du Sud, Asie, Moyen-Orient, Afrique, Océanie.
Les annonces étrangères sont traduites en français. Vos décisions (pas intéressé / candidature envoyée / refus)
sont mémorisées sur cet appareil : une annonce traitée ne réapparaît plus dans « Nouvelles ».<br>
<strong>Dernière mise à jour de la base : __DATE_MAJ__</strong>
</div>

<div id="toolbar" class="toolbar"></div>
<div class="searchbar"><input id="search" type="search" placeholder="Rechercher (compagnie, appareil, pays…)" aria-label="Rechercher dans les annonces"></div>
<div id="countBadge" class="count-badge"></div>
<div id="list"></div>

<footer>
Page générée automatiquement deux fois par jour par un collecteur open source (flux publics gratuits : Google News multilingue, SNPI…).<br>
Base historisée : aucune annonce n'est supprimée — __NB__ annonces collectées à ce jour.
</footer>

<script>
const ANNONCES = __DATA__;

const REGIONS = ["Toutes", "Europe", "Amérique du Nord", "Amérique du Sud", "Asie", "Moyen-Orient", "Océanie", "Afrique", "Monde"];
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

function renderToolbar() {
  const tb = document.getElementById("toolbar");
  tb.innerHTML = "";
  const regionWrap = document.createElement("div");
  regionWrap.style.cssText = "display:flex;gap:6px;flex-wrap:wrap";
  REGIONS.forEach(r => {
    const b = document.createElement("button");
    b.textContent = r;
    if (r === currentRegionFilter) b.classList.add("active");
    b.onclick = () => { currentRegionFilter = r; render(); };
    regionWrap.appendChild(b);
  });
  tb.appendChild(regionWrap);

  const statusWrap = document.createElement("div");
  statusWrap.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-left:auto";
  const allBtn = document.createElement("button");
  allBtn.textContent = "Toutes";
  if (currentStatusFilter === "Toutes") allBtn.classList.add("active");
  allBtn.onclick = () => { currentStatusFilter = "Toutes"; render(); };
  statusWrap.appendChild(allBtn);
  Object.entries(STATUSES).forEach(([key, meta]) => {
    const b = document.createElement("button");
    b.textContent = meta.label;
    if (key === currentStatusFilter) b.classList.add("active");
    b.onclick = () => { currentStatusFilter = key; render(); };
    statusWrap.appendChild(b);
  });
  tb.appendChild(statusWrap);
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

  const totalNouvelles = ANNONCES.filter(a => (statusMap[a.id] || "Nouvelle") === "Nouvelle").length;
  badge.textContent = `${totalNouvelles} annonce(s) nouvelle(s) sur ${ANNONCES.length} affichées — ${items.length} correspondent aux filtres.`;

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


def generer() -> None:
    base = json.loads(FICHIER_DONNEES.read_text(encoding="utf-8"))
    annonces = base["annonces"]

    # Les plus récentes d'abord (date de collecte puis date de publication).
    annonces_triees = sorted(
        annonces,
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

    page = (
        MODELE
        .replace("__DATA__", json.dumps(annonces_triees, ensure_ascii=False))
        .replace("__DATE_MAJ__", date_maj)
        .replace("__NB__", str(len(annonces)))
    )
    FICHIER_SITE.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_SITE.write_text(page, encoding="utf-8")
    print(f"Site généré : {FICHIER_SITE} ({len(annonces_triees)} annonces affichées, {len(annonces)} dans la base)")


if __name__ == "__main__":
    generer()
