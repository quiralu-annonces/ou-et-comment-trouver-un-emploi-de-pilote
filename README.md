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

### Troisième langue

Le candidat maîtrise le français et l'anglais. Une annonce qui réclame une
autre langue est écartée (`langue_bloquante` dans `collecteur/filtres.py`), que
ce soit une langue nommée (« fluent Arabic required », « Chinese speaking ») ou
la formule générique (« la maîtrise d'autres langues locales du pays d'emploi
est un atout »).

Chaque verdict porte deux qualités : sa **nature** (exigence ferme ou simple
atout) et sa **source** — une langue nommée, ou la formule générique « autres
langues locales du pays d'emploi », qui n'en nomme aucune.

`NIVEAU_EXCLUSION_LANGUE` décide de la sévérité :

| Réglage | Ce qui est écarté |
| --- | --- |
| `exigence` | les seules exigences fermes |
| **`langue_locale`** *(actuel)* | + la formule générique, même en simple atout |
| `atout` | + toute langue nommée citée comme simple avantage |

Le niveau retenu sépare ce que les consignes visaient distinctement. La formule
générique ne nomme aucune langue : elle dit que le poste s'exerce dans un pays
dont le candidat ne parle pas la langue, et l'« atout » y est souvent une
politesse. Une langue nommée en simple bonus, à l'inverse, ne disqualifie
personne — « Spanish ICAO Level Proficiency ≥ 4 would be a plus » sur un
copilote A330 basé à Madrid laisse le candidat éligible, l'anglais niveau 4
suffisant à remplir les exigences.

| Annonce | Verdict | Sort |
| --- | --- | --- |
| « la maîtrise d'autres langues locales du pays d'emploi est un atout » | atout / locale | écartée |
| « Deutsch und Englisch in Wort und Schrift erforderlich » | exigence / citée | écartée |
| « Spanish ICAO Level ≥ 4 would be a plus » | atout / citée | conservée |

Sans qualificatif, la mention compte comme une exigence : « Flight Simulator
Instructor – Chinese Speaking » ne présente pas le chinois comme un bonus, il
définit le poste.

Le déclenchement exige un mot de contexte linguistique à moins de 70 caractères
du nom de la langue — sans quoi « Spanish airline », « German operator » ou
« Dutch carrier » seraient écartés à tort, le nom d'une langue et l'adjectif de
nationalité étant le même mot en anglais. Ces mots de contexte existent en
français, en anglais, mais aussi **en allemand, espagnol, italien, portugais et
néerlandais** : une annonce qui exige une langue locale est souvent rédigée dans
cette langue, et « Deutsch und Englisch in Wort und Schrift » passait au
travers faute d'un seul mot de contexte allemand.

`VERSION_ANALYSE_LANGUE` versionne ces motifs. L'incrémenter fait relire les
annonces analysées par une version antérieure : sans ce numéro, une annonce
examinée par une version qui ne savait pas encore lire l'allemand resterait
marquée « aucune exigence » à jamais.

**L'annonce est lue en entier.** Le titre et l'extrait de 400 caractères ne
suffisaient pas : une exigence linguistique se trouve presque toujours sous
« Profil recherché », jamais en vitrine. Le collecteur télécharge donc la fiche
complète, en retire code, navigation, en-tête et pied de page — un sélecteur de
langue « Deutsch / Español » en haut de page ferait croire à une exigence sur
chaque annonce du site — puis examine le texte restant.

Le verdict est enregistré une fois pour toutes sur l'annonce :

```json
"langue_exigee": {"extrait": "fluent Arabic", "nature": "exigence"},
"texte_lu": true
```

Deux économies rendent la chose supportable. Les fiches AllFlyingJobs sont déjà
téléchargées pour en extraire le lieu et la date : leur texte est réutilisé sans
seconde requête. Et une page inaccessible n'est pas comptée comme « lue » —
`texte_lu` reste faux et la fiche sera reprise à l'exécution suivante, plutôt
que d'être tenue pour vierge d'exigence linguistique sur la foi d'un échec
réseau.

Les annonces entrées en base avant cette lecture sont rattrapées
progressivement par `relire_annonces` : à chaque exécution, jusqu'à
`RELECTURE_MAX` fiches encore affichables sont relues. La veille tournant deux
fois par jour, le retard se résorbe en quelques passages.

## Compagnies suivies nommément

`collecteur/compagnies.py` recense 19 compagnies françaises, ultramarines et
d'aviation d'affaires interrogées à chaque collecte. Toutes n'exposent pas leurs
offres de la même façon, et le registre le dit explicitement plutôt que de
laisser croire à une couverture automatique complète :

**Veille automatique (6)** — une offre publiée est collectée toute seule :

| Compagnie | Mode | Point d'entrée |
| --- | --- | --- |
| Groupe Air Tahiti | `rss` | flux Teamtailor `carrieres.airtahiti.com/jobs.rss` |
| Aircalin | `liste` | `carrieres.aircalin.com` (liste d'offres HTML) |
| Air Calédonie | `sitemap` | `air-caledonie.nc/recrutements-sitemap.xml` |
| Air Tahiti Nui | `sitemap` | `us.airtahitinui.com/sitemap.xml` (pages Drupal) |
| Amelia (Regourd Aviation) | `recruitee` | API JSON `career.flyamelia.com/api/offers/` |
| La Compagnie | `liste` | `careers.werecruit.io/fr/la-compagnie` |

**Décompte seul (2)** — French bee et Air Caraïbes tournent toutes deux sur
CVCatcher (groupe HelloWork) : leur plan de site liste une URL par offre
ouverte, mais chaque fiche est une coquille vide remplie par une API qui exige
une authentification (`api.cvcatcher.io/v2/job-offers` → HTTP 401). Aucun
intitulé n'est lisible. Le collecteur relève donc le **nombre d'offres
ouvertes**, affiché à côté du lien : savoir qu'il y en a cinq plutôt qu'aucune
est ce qui décide d'ouvrir le portail.

**À consulter à la main (11)** — Corsair, Air Corsica, Finist'air, Air Austral,
Air Moana, Air Saint-Pierre, Air Loyauté, VallJet, Astonjet, IXair, Pan
Européenne. Aucune ne publie de liste de postes lisible : la plupart n'ont
aucune liste du tout et renvoient vers une adresse de candidature ; Air Austral
refuse le robot jusqu'à sa page d'accueil (HTTP 403, alors que son `robots.txt`
autorise tout — c'est un pare-feu, pas une interdiction d'indexation). Elles
sont publiées sur le site dans le dépliant « compagnies suivies », avec le lien
direct et l'adresse de candidature quand elle est connue.

**Facebook n'est pas exploitable.** Plusieurs de ces compagnies (Air
Saint-Pierre notamment) publient leurs offres sur leur page Facebook. Ni
`facebook.com` ni `mbasic.facebook.com` ne servent le contenu d'une page sans
compte connecté : les deux renvoient un mur de connexion. L'API Graph, elle,
exige un jeton d'accès délivré à l'administrateur de la page. Il n'existe donc
pas de voie automatique, et les conditions d'utilisation de Facebook
interdisent le moissonnage.

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
