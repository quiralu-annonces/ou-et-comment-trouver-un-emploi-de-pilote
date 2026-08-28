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
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apprentissage import (  # noqa: E402
    charger_decisions,
    deduire_regles,
    evaluer,
    resume,
)
from criteres import libelle as libelle_critere  # noqa: E402
from profil import atouts as atouts_profil, ecarts as ecarts_profil  # noqa: E402
from compagnies import COMPAGNIES, MODES_AUTOMATIQUES  # noqa: E402
from filtres import criteres_presents, motif_exclusion, texte_annonce  # noqa: E402

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

# Chaîne BRUTE (r"""). Sans le préfixe r, Python interprète les séquences
# d'échappement du gabarit : un « \n » écrit dans un message JavaScript
# devenait une vraie fin de ligne, coupait la chaîne en deux et rendait tout
# le script invalide — donc la page muette, sans filtres ni annonces. Le
# préfixe r supprime cette classe d'erreur à la racine.
MODELE = r"""<!DOCTYPE html>
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
  /* Marqueurs du profil recherché : mis en avant, ce sont eux qui justifient
     la présence de l'annonce dans la liste. */
  .tag.critere { color: var(--accent-2); border-color: var(--accent-2); }
  /* Critères appris des décisions : le vert dit « proche de ce que vous avez
     retenu », le rouge « proche de ce que vous avez écarté ». */
  .tag.favorable { color: var(--success); border-color: var(--success); }
  .tag.defavorable { color: var(--danger); border-color: var(--danger); }
  .tag.examen { color: #0f1416; background: var(--accent-2); border-color: var(--accent-2); font-weight: 700; }
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

  /* Rappel d'export : assez visible pour ne pas être manqué, assez sobre pour
     ne pas passer devant les annonces, qui restent le contenu principal. */
  .rappel {
    display: flex; gap: 14px; align-items: center; justify-content: space-between;
    flex-wrap: wrap;
    background: var(--panel-2); border: 1px solid var(--accent-2);
    border-left: 4px solid var(--accent-2);
    border-radius: var(--radius); padding: 12px 16px; margin-bottom: 16px; font-size: 13px;
  }
  .rappel-detail { color: var(--text-dim); font-size: 12px; line-height: 1.6; margin-top: 5px; }
  .rappel code { background: var(--panel); padding: 1px 5px; border-radius: 4px; }
  .rappel button {
    background: var(--accent-2); color: #0f1416; border: none; border-radius: 6px;
    padding: 9px 16px; font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap;
  }

  /* Compagnies suivies : dépliant fermé par défaut, il ne doit pas repousser
     les annonces — c'est un aide-mémoire, pas le contenu principal. */
  details.compagnies {
    background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 12px 16px; margin-bottom: 16px;
  }
  details.compagnies > summary { cursor: pointer; font-size: 14px; font-weight: 600; }
  details.compagnies p { font-size: 12px; color: var(--text-dim); line-height: 1.6; }
  ul.compagnies { list-style: none; padding: 0; margin: 10px 0 0; }
  ul.compagnies li { padding: 7px 0; border-top: 1px solid var(--border); font-size: 13px; }
  ul.compagnies a { color: var(--accent); text-decoration: none; font-weight: 600; }
  ul.compagnies a:hover { text-decoration: underline; }
  ul.compagnies .auto { color: var(--success); font-size: 11px; }
  ul.compagnies .manuel { color: var(--accent-2); font-size: 11px; }
  ul.compagnies .detail { color: var(--text-dim); font-size: 12px; display: block; margin-top: 2px; }
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
Veille mondiale automatique des offres d'emploi de pilote de ligne, copilote et cadet —
Europe, Canada / Québec, Amérique du Sud, Asie, Moyen-Orient, Afrique, Océanie.
Les annonces étrangères sont traduites en français. Vos décisions (pas intéressé / candidature envoyée / refus)
sont mémorisées sur cet appareil : une annonce traitée ne réapparaît plus dans « Nouvelles ».<br>
Seules les annonces parues <strong>depuis moins d'un mois</strong> sont affichées. Les offres situées
aux <strong>États-Unis</strong> ne sont pas retenues, ni celles qui <strong>exigent une troisième
langue</strong> au-delà du français et de l'anglais, ni celles qui réclament « la maîtrise des
langues locales du pays d'emploi ». Une langue précise citée comme simple atout n'écarte pas
l'annonce : le poste reste accessible.<br>
Les annonces sont confrontées au dossier réel du candidat — <strong>290 heures de vol, anglais
niveau 4, EASA ATPL, aucune qualification de type</strong>. Sont écartés les postes de
<strong>maintenance seule</strong> (un poste mixte pilotage-maintenance, lui, est conservé), ceux
exigeant un niveau de langue supérieur, et ceux dont le plancher d'heures est hors d'atteinte.<br>
Chaque annonce publiée porte au moins un des marqueurs du profil recherché — <strong>pilote ou copilote,
entry level, minimum 300 heures de vol, anglais niveau 4, non type rated, EASA ATPL, first officer</strong> —
signalés en jaune sur la fiche.<br>
<strong>Dernière mise à jour de la base : __DATE_MAJ__</strong>
</div>

<div id="toolbar" class="toolbar"></div>
<div class="searchbar"><input id="search" type="search" placeholder="Rechercher (compagnie, appareil, pays…)" aria-label="Rechercher dans les annonces"></div>
<div id="countBadge" class="count-badge"></div>
<div id="rappel"></div>
<div id="list"></div>

<!-- Les dépliants viennent APRÈS les annonces : ce sont des aide-mémoire, pas
     le contenu principal. Placés avant, ils repoussaient la liste hors de
     l'écran dès qu'on les ouvrait. -->
__COMPAGNIES__
__APPRENTISSAGE__

<footer>
Page générée automatiquement deux fois par jour par un collecteur open source (bourses d'emploi publiques : SNPI, FFVP, AllFlyingJobs…).<br>
__NB_AFFICHEES__ annonce(s) affichée(s) : parues depuis moins d'un mois, hors États-Unis, portant au moins un marqueur du profil recherché.<br>
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
const CLE_EXPORT = "veille-pilote:dernier-export";
/* En dessous de trois décisions, un export n'apprendrait rien : les seuils du
   collecteur demandent qu'un critère se répète. Réclamer l'export dès le
   premier clic ne ferait qu'habituer à ignorer le message. */
const SEUIL_RAPPEL = 3;
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
  const exporter = mkBtn("⬇ Exporter mes décisions", false, exporterDecisions);
  exporter.title = "Produit un fichier decisions.json à déposer dans data/ du dépôt : "
    + "le collecteur y apprend ce que vous écartez.";
  exporter.style.marginLeft = "auto";
  rowStatus.appendChild(exporter);
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
  const criteres = (a.criteres || [])
    .map(c => `<span class="tag critere">✓ ${echap(c)}</span>`).join("");
  /* Critères appris de VOS décisions, distincts des marqueurs du profil :
     les favorables viennent de vos candidatures, les défavorables de vos
     refus. Les deux ensembles ne se mélangent jamais. */
  const favorables = (a.favorables || [])
    .map(c => `<span class="tag favorable">▲ ${echap(c)}</span>`).join("");
  const defavorables = (a.defavorables || [])
    .map(c => `<span class="tag defavorable">▼ ${echap(c)}</span>`).join("");
  const examen = a.issue === "examiner"
    ? `<span class="tag examen">⚠ À examiner — ressemble à vos refus (score ${a.score})</span>` : "";
  /* Confrontation à votre dossier : ce que vous détenez, ce qui vous manque.
     Ces mentions n'écartent rien, elles évitent d'ouvrir pour rien. */
  const atouts = (a.atouts || [])
    .map(c => `<span class="tag favorable">✔ vous avez : ${echap(c)}</span>`).join("");
  const ecarts = (a.ecarts || [])
    .map(c => `<span class="tag defavorable">✖ ${echap(c)}</span>`).join("");
  return `
  <div class="card ${dismissedCls}">
    <div class="card-title">${echap(a.titre_fr)}</div>
    ${original}
    <div class="card-sub">${echap(a.source)}${datePub} — repérée le ${dateCourte(a.premiere_collecte)}</div>
    <div class="tags">
      <span class="tag">${echap(a.region)}</span>
      <span class="tag">${echap((a.langue || "").toUpperCase())}</span>
      <span class="tag ${statusMeta.cls}">${statusMeta.label === "Nouvelles" ? "Nouvelle" : statusMeta.label}</span>
      ${criteres}${atouts}${ecarts}${favorables}${defavorables}${examen}
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

/* Les décisions vivent dans ce navigateur : le collecteur, qui tourne sur un
   serveur distant deux fois par jour, ne peut pas les lire. Cet export est le
   seul pont entre les deux. Il ne contient que des identifiants et des statuts
   — le texte des annonces est déjà en base, inutile de le renvoyer. */
/* On lit le stockage du navigateur, PAS la liste affichée. Une annonce quitte
   la page au bout d'un mois, mais la décision prise dessus reste mémorisée :
   parcourir ANNONCES perdait tout l'historique, c'est-à-dire justement ce dont
   l'apprentissage a le plus besoin. Le collecteur, lui, retrouve ces annonces
   — sa base ne supprime jamais rien. */
function decisionsMemorisees() {
  const decisions = {};
  for (let i = 0; i < localStorage.length; i++) {
    const cle = localStorage.key(i);
    if (!cle || cle.indexOf(CLE) !== 0) continue;
    const statut = localStorage.getItem(cle);
    if (!statut || statut === "Nouvelle") continue;
    decisions[cle.slice(CLE.length)] = statut;
  }
  return decisions;
}

function exporterDecisions() {
  const decisions = decisionsMemorisees();
  const affichees = new Set(ANNONCES.map(a => a.id));
  let horsPage = 0;
  for (const id of Object.keys(decisions)) if (!affichees.has(id)) horsPage++;
  const nb = Object.keys(decisions).length;
  if (!nb) {
    alert("Aucune décision à exporter. Marquez d'abord des annonces « Pas intéressé » ou « Candidature envoyée ».");
    return;
  }
  alert(nb + " décision(s) exportée(s), dont " + horsPage
    + " sur des annonces qui ne sont plus affichées. Déposez le fichier dans data/decisions.json du dépôt.");
  const contenu = JSON.stringify(
    { version: 1, exporte_le: new Date().toISOString(), decisions }, null, 1);
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(new Blob([contenu], { type: "application/json" }));
  lien.download = "decisions.json";
  lien.click();
  URL.revokeObjectURL(lien.href);
  /* On retient combien de décisions ont été exportées : le rappel ne
     réapparaîtra qu'après de NOUVELLES décisions, et pas à chaque visite. */
  try { localStorage.setItem(CLE_EXPORT, String(nb)); } catch (e) { console.error(e); }
  render();
}

/* Les décisions restent dans ce navigateur tant qu'on ne les exporte pas. Rien
   ne le disait : on pouvait trier des dizaines d'annonces en croyant que le
   système en tenait compte, alors qu'il n'en voyait aucune. Ce rappel n'appa-
   raît qu'une fois le tri commencé, et disparaît dès l'export. */
function renderRappel() {
  const zone = document.getElementById("rappel");
  const nb = Object.keys(decisionsMemorisees()).length;
  const exportees = parseInt(localStorage.getItem(CLE_EXPORT) || "0", 10);

  if (nb < SEUIL_RAPPEL || nb <= exportees) { zone.innerHTML = ""; return; }

  const nouvelles = nb - exportees;
  zone.innerHTML = `
    <div class="rappel">
      <div>
        <strong>${nb} décision${nb > 1 ? "s" : ""} enregistrée${nb > 1 ? "s" : ""} sur cet appareil</strong>
        ${exportees ? ` — dont ${nouvelles} depuis votre dernier export` : ""}.
        <div class="rappel-detail">
          Elles ne quittent pas ce navigateur : le collecteur ne les voit pas et n'apprend
          rien tant qu'elles n'ont pas été exportées. Exportez le fichier, puis transmettez-le
          pour qu'il soit déposé dans <code>data/decisions.json</code> du dépôt.
        </div>
      </div>
      <button onclick="exporterDecisions()">⬇ Exporter maintenant</button>
    </div>`;
}

function render() {
  renderToolbar();
  renderRappel();
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
    `<strong>${ANNONCES.length}</strong> retenue(s) au total — parues depuis moins d'un mois, hors États-Unis, ` +
    `portant au moins un marqueur du profil recherché.` +
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


def appliquer_regles(annonces: list[dict], regles: dict | None = None) -> tuple[list[dict], dict[str, int]]:
    """Applique les deux règles d'affichage et reclasse le Canada.

    Renvoie les annonces retenues et un compte-rendu chiffré des exclusions,
    pour que la restriction ne soit jamais silencieuse.
    """
    limite = datetime.now(timezone.utc) - timedelta(days=FENETRE_JOURS)
    retenues: list[dict] = []
    regles = regles or {}
    stats = {
        "actualites": 0, "nationalite": 0, "langue": 0, "criteres": 0,
        "trop_anciennes": 0, "sans_date": 0, "etats_unis": 0, "canada": 0,
        "appris": 0, "a_examiner": 0,
        "maintenance": 0, "niveau_langue": 0, "heures": 0,
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
        if motif == "langue":
            # Une troisième langue est réclamée : le candidat ne l'a pas.
            stats["langue"] += 1
            continue
        if motif == "criteres":
            # Aucun des huit marqueurs du profil : l'annonce ne s'adresse pas
            # au candidat, quelle que soit sa fraîcheur.
            stats["criteres"] += 1
            continue
        if motif in ("maintenance", "niveau_langue", "heures"):
            # Incompatible avec le profil réel : poste de maintenance seule,
            # langue au-dessus du niveau détenu, plancher d'heures hors portée.
            stats[motif] += 1
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

        # Règles apprises des décisions : elles s'appliquent en dernier, après
        # les règles fixes, pour qu'un motif appris ne masque jamais la vraie
        # raison d'une exclusion dans le compte-rendu.
        verdict = evaluer(annonce, regles)
        if verdict["issue"] == "ecarter":
            stats["appris"] += 1
            continue
        if verdict["issue"] == "examiner":
            stats["a_examiner"] += 1

        # Chaque annonce porte les marqueurs qui lui ont valu d'être retenue :
        # affichés sur la fiche, ils disent en un coup d'œil pourquoi elle est là.
        retenues.append({
            **annonce,
            "criteres": criteres_presents(texte_annonce(annonce)),
            "score": verdict["score"],
            "issue": verdict["issue"],
            "favorables": [libelle_critere(m) for m in verdict["favorables"]],
            "ecarts": ecarts_profil(annonce),
            "atouts": atouts_profil(annonce),
            "defavorables": [libelle_critere(m) for m in verdict["defavorables"]],
        })

    return retenues, stats


def _echapper(texte: str) -> str:
    return (
        str(texte or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def bloc_compagnies(compteurs: dict | None = None) -> str:
    """Dépliant listant les compagnies suivies et le mode de veille de chacune.

    Les compagnies dont la page carrières n'est pas moissonnable (rendue en
    JavaScript, protégée, ou sans autre porte d'entrée qu'une adresse de
    candidature) figurent ici avec leur lien : c'est le seul moyen honnête de
    les « ajouter à la recherche » sans laisser croire qu'un robot s'en occupe.
    """
    compteurs = compteurs or {}
    auto = [c for c in COMPAGNIES if c["mode"] in MODES_AUTOMATIQUES]
    lignes = []
    for compagnie in COMPAGNIES:
        automatique = compagnie["mode"] in MODES_AUTOMATIQUES
        badge = (
            '<span class="auto">● veille automatique</span>'
            if automatique
            else '<span class="manuel">● à consulter vous-même</span>'
        )
        # Portail à intitulés illisibles : le décompte relevé à la collecte
        # remplace le badge, c'est lui qui dit s'il faut aller voir.
        if compagnie["mode"] == "compteur":
            releve = compteurs.get(compagnie["nom"], {}).get("offres_ouvertes")
            if releve is None:
                badge = '<span class="manuel">● à consulter vous-même</span>'
            elif releve > 0:
                badge = f'<span class="auto">● {releve} offre(s) ouverte(s) — titres non lisibles</span>'
            else:
                badge = '<span class="manuel">● aucune offre ouverte</span>'
        precisions = []
        if compagnie.get("note"):
            precisions.append(_echapper(compagnie["note"]))
        if compagnie.get("contact"):
            adresse = _echapper(compagnie["contact"])
            precisions.append(f'Candidature : <a href="mailto:{adresse}">{adresse}</a>')
        detail = (
            f'<span class="detail">{" — ".join(precisions)}</span>' if precisions else ""
        )
        lignes.append(
            f'<li><a href="{_echapper(compagnie["page"])}" target="_blank" rel="noopener">'
            f'{_echapper(compagnie["nom"])} ↗</a> {badge}{detail}</li>'
        )

    comptees = [c for c in COMPAGNIES if c["mode"] == "compteur"]
    manuelles = len(COMPAGNIES) - len(auto) - len(comptees)
    return (
        '<details class="compagnies">\n'
        f"<summary>✈️ {len(COMPAGNIES)} compagnies suivies nommément "
        f"({len(auto)} en veille automatique, {len(comptees)} en décompte, "
        f"{manuelles} à consulter vous-même)</summary>\n"
        "<p>Les pages carrières marquées « veille automatique » sont interrogées à chaque "
        "collecte : leurs offres de pilotage apparaissent dans la liste ci-dessous. Pour deux "
        "portails, seul le nombre d'offres ouvertes est lisible, pas leur intitulé : le décompte "
        "vous dit s'il vaut la peine d'aller voir. Les dernières ne publient aucune liste "
        "exploitable (candidature par courriel, ou site fermé aux robots) : ouvrez-les "
        "vous-même, le lien est direct.</p>\n"
        f'<ul class="compagnies">{"".join(lignes)}</ul>\n'
        "</details>"
    )


def bloc_apprentissage(regles: dict, nb_ecartees: int) -> str:
    """Dépliant listant les règles déduites des refus, et ce qu'elles coûtent.

    Le filtrage est silencieux — l'utilisateur l'a demandé — mais il ne doit pas
    être invisible : une règle tirée de quelques clics peut se tromper, et on ne
    peut la corriger que si l'on sait qu'elle existe.
    """
    if not regles.get("nb_refus") and not regles.get("nb_candidatures"):
        return ""

    def lignes(motifs: dict) -> str:
        return "".join(
            f'<li><code>{_echapper(motif)}</code> '
            f'<span class="detail">refusée {p["refus"]} fois sur {p["total"]} '
            f'annonces qui la portent ({p["taux"]:.0%})</span></li>'
            for motif, p in sorted(motifs.items(), key=lambda x: -x[1]["refus"])
        )

    def lignes_favorables(motifs: dict) -> str:
        return "".join(
            f'<li><code>{_echapper(libelle_critere(motif))}</code> '
            f'<span class="detail">retenu {p["candidatures"]} fois sur {p["total"]} '
            f'annonces qui le portent ({p["taux"]:.0%}) — poids +{p["poids"]}</span></li>'
            for motif, p in sorted(motifs.items(), key=lambda x: -x[1]["candidatures"])
        )

    corps = ""
    if regles.get("favorables"):
        corps += (
            f"<p><strong>{len(regles['favorables'])} critère(s) favorable(s)</strong>, déduits de vos "
            f"candidatures envoyées. Une annonce qui les porte remonte dans la liste :</p>"
            f'<ul class="compagnies">{lignes_favorables(regles["favorables"])}</ul>'
        )
    elif regles["nb_candidatures"]:
        corps += (
            "<p>Aucun critère favorable pour l'instant : aucun ne se répète assez d'une "
            "candidature à l'autre pour être tenu pour représentatif.</p>"
        )
    if regles["exclusions"]:
        corps += (
            f"<p><strong>{len(regles['exclusions'])} motif(s) écartent automatiquement une annonce</strong> "
            f"— {nb_ecartees} annonce(s) masquée(s) à ce titre :</p>"
            f'<ul class="compagnies">{lignes(regles["exclusions"])}</ul>'
        )
    else:
        corps += "<p>Aucun motif ne franchit encore les seuils d'exclusion automatique.</p>"
    if regles["penalites"]:
        corps += (
            "<p>Motifs simplement <strong>pénalisés</strong> : les annonces concernées "
            "descendent en bas de liste, elles restent consultables.</p>"
            f'<ul class="compagnies">{lignes(regles["penalites"])}</ul>'
        )
    if regles.get("signaux"):
        corps += (
            "<p><strong>Signaux repérés mais non appris</strong> — ils n'écartent rien et ne "
            "pénalisent rien. Le tri n'apprend que sur un vocabulaire décrivant le poste, "
            "jamais sur un nom d'employeur ; ces mots-là reviennent pourtant dans vos refus. "
            "Si l'un d'eux décrit un contenu (un rythme, une mission, une contrainte) plutôt "
            "qu'une compagnie, signalez-le : il deviendra un critère.</p>"
            '<ul class="compagnies">'
            + "".join(
                f'<li><code>{_echapper(s["mot"])}</code> '
                f'<span class="detail">{s["refus"]} de vos refus sur {s["total"]} '
                f'annonces contenant ce mot ({s["taux"]:.0%})</span></li>'
                for s in regles["signaux"]
            )
            + "</ul>"
        )

    return (
        '<details class="compagnies">\n'
        f"<summary>🧠 Règles apprises de vos refus "
        f"({len(regles['exclusions'])} exclusion(s), {len(regles['penalites'])} pénalité(s))</summary>\n"
        f"<p>Déduites de {regles['nb_refus']} annonce(s) que vous avez écartée(s) et de "
        f"{regles['nb_candidatures']} candidature(s) envoyée(s). Un motif présent dans une annonce "
        f"à laquelle vous avez postulé ne peut jamais devenir une exclusion.</p>\n"
        f"{corps}\n</details>"
    )


def verifier_javascript(page: str) -> None:
    """Refuse de publier une page dont le script ne compile pas.

    Toute l'interface — filtres, liste, boutons de décision — est construite
    par ce script. Une seule erreur de syntaxe et la page ne montre plus que
    son HTML statique : ni annonces, ni boutons. C'est arrivé, et rien ne le
    signalait puisque le fichier était généré sans erreur côté Python.

    Le contrôle s'appuie sur Node quand il est disponible — c'est le cas sur
    GitHub Actions. Sinon il est passé : mieux vaut une vérification parfois
    absente qu'une génération impossible sur un poste sans Node.
    """
    script = re.search(r"<script>(.*?)</script>", page, re.DOTALL)
    if not script:
        raise SystemExit("Page générée sans bloc <script> : génération interrompue.")
    if not shutil.which("node"):
        print("  (Node absent : syntaxe du script non vérifiée)")
        return

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script.group(1))
        chemin = f.name
    try:
        resultat = subprocess.run(
            ["node", "--check", chemin], capture_output=True, text=True, timeout=30
        )
    finally:
        Path(chemin).unlink(missing_ok=True)

    if resultat.returncode != 0:
        raise SystemExit(
            "Le script de la page ne compile pas — publication interrompue.\n"
            f"{resultat.stderr.strip()}"
        )
    print("  script vérifié : syntaxe valide")


def generer() -> None:
    base = json.loads(FICHIER_DONNEES.read_text(encoding="utf-8"))
    annonces = base["annonces"]

    decisions = charger_decisions()
    # L'apprentissage ne compare qu'aux annonces que l'utilisateur a pu voir.
    # Mesurer un motif sur la base entière le dilue dans 400 articles de presse
    # jamais affichés : « région Moyen-Orient », refusée huit fois sur huit,
    # semblait alors n'être refusée qu'une fois sur dix.
    corpus = [a for a in annonces if motif_exclusion(a) is None]
    regles = deduire_regles(corpus, decisions)
    retenues, stats = appliquer_regles(annonces, regles)

    # Score d'abord, fraîcheur ensuite : une annonce proche de ce que
    # l'utilisateur a déjà refusé descend, sans jamais disparaître.
    annonces_triees = sorted(
        retenues,
        key=lambda a: (
            a.get("score", 0),
            a.get("premiere_collecte") or "",
            a.get("date_publication") or "",
        ),
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
        .replace("__COMPAGNIES__", bloc_compagnies(base.get("compagnies")))
        .replace("__APPRENTISSAGE__", bloc_apprentissage(regles, stats["appris"]))
        .replace("__COCKPIT__", cockpit)
    )
    # Vérifier AVANT d'écrire : une page cassée ne doit pas remplacer la
    # précédente, qui elle fonctionnait.
    verifier_javascript(page)

    FICHIER_SITE.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_SITE.write_text(page, encoding="utf-8")
    print(
        f"Site généré : {FICHIER_SITE}\n"
        f"  {len(annonces_triees)} offre(s) affichée(s) sur {len(annonces)} entrées en base\n"
        f"  écartées : {stats['actualites']} actualités (pas des offres), "
        f"{stats['nationalite']} nationalité exigée non détenue,\n"
        f"             {stats['langue']} exigeant une 3e langue, "
        f"{stats['criteres']} sans aucun marqueur du profil recherché, "
        f"{stats['trop_anciennes']} de plus de {FENETRE_JOURS} jours, "
        f"{stats['etats_unis']} aux États-Unis, {stats['sans_date']} sans date exploitable\n"
        f"             {stats['maintenance']} maintenance seule, {stats['niveau_langue']} langue au-dessus du niveau, "
        f"{stats['heures']} heures hors de portée,\n"
        f"             {stats['appris']} sur une règle apprise des refus "
        f"({stats['a_examiner']} signalée(s) « à examiner », affichée(s))\n"
        f"  reclassées « {REGION_CANADA} » : {stats['canada']}\n"
        f"\n--- Rapport d'ajustement ---\n{resume(regles)}"
    )


if __name__ == "__main__":
    generer()
