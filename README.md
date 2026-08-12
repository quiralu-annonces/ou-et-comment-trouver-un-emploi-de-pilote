# Où et comment trouver un emploi de pilote d'avion

Veille mondiale automatique et **100 % gratuite** des offres d'emploi de pilote :
pilote de ligne, copilote (First Officer), programmes cadets, pilote d'affaires
— sur toutes les régions du monde (Europe, Amérique du Nord, Amérique du Sud,
Asie, Moyen-Orient, Afrique, Océanie).

Le site publie un tableau de bord unique où chaque visiteur peut trier les
annonces (« Pas intéressé », « Candidature envoyée », « Refus reçu ») ; ses
décisions sont mémorisées dans son navigateur et les annonces traitées ne
réapparaissent plus.

## Comment ça marche

```
[Bourses d'emploi : SNPI, FFVP, AllFlyingJobs]
[Pages carrières des 19 compagnies suivies (collecteur/compagnies.py)]
        │  2 fois par jour (GitHub Actions, gratuit)
        ▼
[collecteur/collecte.py]  filtre pilote + marqueurs du profil, traduit en
        │                 français, déduplique, ajoute à la base (jamais de
        │                 suppression)
        ▼
[data/annonces.json]      base historisée append-only
        │
        ▼
[collecteur/genere_site.py] → docs/index.html (site statique GitHub Pages)
```

- **Aucun coût** : sources publiques gratuites, traduction gratuite
  (deep-translator), hébergement GitHub Pages gratuit, automatisation GitHub
  Actions gratuite (dépôt public).
- **Aucune donnée supprimée** : la base `data/annonces.json` est append-only.
- **Identifiants stables** : les décisions des visiteurs (stockées en
  localStorage sous `veille-pilote:status:<id>`) survivent aux mises à jour.

## Critères de sélection des annonces

Une offre n'est publiée que si elle porte **au moins un** des sept marqueurs du
profil recherché (`CRITERES_REQUIS` dans `collecteur/filtres.py`) :

| Marqueur | Reconnu aussi sous |
| --- | --- |
| Pilote / copilote | pilot, pilots, copilot, co-pilot, piloto |
| Entry level | ab initio, low hours, no experience, débutant, cadet |
| Minimum 300 heures de vol | toute expérience exigée ≤ 500 h (`SEUIL_HEURES_VOL`) adossée à un mot de vol — « 40 hours per week » ne compte pas |
| Anglais niveau 4 | ICAO/OACI level 4-5-6, ELP 4, language proficiency, FCL.055 |
| Non type rated | no type rating, type rating not required, sans qualification de type |
| EASA ATPL | frozen ATPL, ATPL(A), ATPL gelé, ATPL théorique |
| First officer | second officer, F/O, OPL, officier pilote de ligne |
| Instructeur / FI | FI(A), FI(S), flight instructor, TRI, TRE, SFI, FCL.9xx |

Les marqueurs trouvés sont affichés en jaune sur chaque fiche du site : on voit
d'un coup d'œil pourquoi l'annonce est retenue.

Conséquence assumée : un poste de **commandant de bord expérimenté** (« Direct
Entry Captain », « minimum 5000 hours ») ne porte aucun de ces marqueurs et
n'est pas publié, non plus qu'un poste au sol ou de mécanicien. S'y ajoutent les
règles déjà en place : offre d'emploi uniquement (jamais un article de presse),
parution de moins d'un mois, hors États-Unis, hors nationalité exigée non
détenue.

## Compagnies suivies nommément

`collecteur/compagnies.py` recense 19 compagnies françaises, ultramarines et
d'aviation d'affaires interrogées à chaque collecte. Toutes n'exposent pas leurs
offres de la même façon, et le registre le dit explicitement plutôt que de
laisser croire à une couverture automatique complète :

**Veille automatique (5)** — une offre publiée est collectée toute seule :

| Compagnie | Mode | Point d'entrée |
| --- | --- | --- |
| Groupe Air Tahiti | `rss` | flux Teamtailor `carrieres.airtahiti.com/jobs.rss` |
| Aircalin | `liste` | `carrieres.aircalin.com` (liste d'offres HTML) |
| Air Calédonie | `sitemap` | `air-caledonie.nc/recrutements-sitemap.xml` |
| Amelia (Regourd Aviation) | `recruitee` | API JSON `career.flyamelia.com/api/offers/` |
| La Compagnie | `liste` | `careers.werecruit.io/fr/la-compagnie` |

**À consulter à la main (14)** — French bee, Corsair, Air Corsica, Finist'air,
Air Caraïbes, Air Austral, Air Tahiti Nui, Air Moana, Air Saint-Pierre, Air
Loyauté, VallJet, Astonjet, IXair, Pan Européenne. Leur page carrières est
rendue en JavaScript, protégée (HTTP 403), ou se réduit à une adresse de
candidature : aucun robot ne peut en tirer d'offre. Elles sont donc publiées sur
le site dans un dépliant « compagnies suivies », avec le lien direct et
l'adresse de candidature quand elle est connue — c'est la seule façon honnête de
les intégrer à la recherche.

Le classement a été établi en sondant chaque site le 12 août 2026. Une compagnie
qui ouvrirait un vrai portail d'offres passe en veille automatique en changeant
sa seule ligne dans `compagnies.py`.

## Lancer en local

```bash
pip install -r collecteur/requirements.txt
python collecteur/collecte.py      # récupère les nouvelles annonces
python collecteur/genere_site.py   # régénère docs/index.html
```

Puis ouvrir `docs/index.html` dans un navigateur.

## Mise en ligne (une seule fois)

1. Créer un dépôt **public** sur GitHub nommé
   `ou-et-comment-trouver-un-emploi-de-pilote`.
2. Pousser ce dossier dessus (`git push`).
3. Dans le dépôt GitHub : **Settings → Pages → Source : Deploy from a branch →
   Branch : `main`, dossier `/docs` → Save**.
4. Dans l'onglet **Actions**, autoriser les workflows si demandé.

Le site est alors accessible à l'adresse :
`https://<votre-compte>.github.io/ou-et-comment-trouver-un-emploi-de-pilote/`
et se met à jour tout seul deux fois par jour (7h15 et 15h15, heure de Paris).

## Ajuster

- **Fréquence** : modifier le `cron` dans `.github/workflows/veille.yml`.
- **Sources / mots-clés** : modifier `SOURCES`, `MOTS_PILOTE` et
  `MOTS_RECRUTEMENT` dans `collecteur/collecte.py`.
- **Critères du profil** : modifier `CRITERES_REQUIS` (et `SEUIL_HEURES_VOL`)
  dans `collecteur/filtres.py`.
- **Compagnies suivies** : ajouter une entrée à `COMPAGNIES` dans
  `collecteur/compagnies.py` (`mode: "manuel"` suffit pour l'afficher dans le
  dépliant du site sans écrire de collecteur).
- **Annonce manuelle** : ajouter une entrée dans `data/annonces.json` (avec un
  champ `details` pour une fiche détaillée) puis regénérer le site.
