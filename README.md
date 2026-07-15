# Où et comment trouver un emploi de pilote d'avion

Veille mondiale automatique et **100 % gratuite** des offres d'emploi de pilote :
pilote de ligne, copilote (First Officer), programmes cadets, pilote d'affaires,
instructeur FI — sur toutes les régions du monde (Europe, Amérique du Nord,
Amérique du Sud, Asie, Moyen-Orient, Afrique, Océanie).

Le site publie un tableau de bord unique où chaque visiteur peut trier les
annonces (« Pas intéressé », « Candidature envoyée », « Refus reçu ») ; ses
décisions sont mémorisées dans son navigateur et les annonces traitées ne
réapparaissent plus.

## Comment ça marche

```
[Sources gratuites : Google News multilingue (fr, en, es, pt, ar, zh, ja, ru, de) + SNPI]
        │  2 fois par jour (GitHub Actions, gratuit)
        ▼
[collecteur/collecte.py]  filtre pilote+recrutement, traduit en français,
        │                 déduplique, ajoute à la base (jamais de suppression)
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
- **Annonce manuelle** : ajouter une entrée dans `data/annonces.json` (avec un
  champ `details` pour une fiche détaillée) puis regénérer le site.
