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

## Le profil du candidat

`collecteur/profil.py` décrit le dossier réel du candidat, en un seul endroit
pour qu'il suive son évolution — ses heures augmenteront, son anglais peut
passer au niveau 5, une qualification de type peut s'ajouter :

| Élément | Valeur |
| --- | --- |
| Heures de vol | 290 dont 144 PIC |
| Anglais | FCL.055 (ELP) niveau 4 |
| Français | langue maternelle |
| Licences | EASA ATPL, CPL/MEP, ME/IR |
| Certificats | Classe 1, MCC/JOC, Advanced UPRT |
| Qualification de type | **aucune** |

Trois règles en découlent, appliquées après tous les autres filtres et
seulement sur les annonces lues en entier — une annonce non encore relue n'est
jamais écartée sur une supposition :

**Maintenance seule.** Le candidat vient de la maintenance — Part-66 B1, CAT A,
dix ans sur Falcon, Bombardier et A320 — et cherche un poste de **pilote**. Ces
annonces lui correspondent parfaitement sur le papier sans l'intéresser. Un
poste **mixte pilotage-maintenance**, en revanche, lui convient : la présence
d'un seul mot de pilotage suffit à conserver l'annonce.

**Niveau de langue au-dessus du sien.** Un poste exigeant un anglais niveau 5
ou 6 est hors d'atteinte avec un FCL.055 niveau 4.

**Plancher d'heures inatteignable.** La comparaison porte sur le **minimum**
exigé par l'annonce, jamais sur le maximum : une fiche proposant un copilote à
250 h et un commandant à 3000 h reste ouverte par le bas. Seuil dans
`SEUIL_HEURES_HORS_PORTEE`.

Les fiches affichent en outre ce que le candidat **détient** parmi les critères
réclamés (vert) et ce qui lui **manque** (rouge) — sans que ces mentions
écartent quoi que ce soit. Elles évitent d'ouvrir une annonce pour rien.

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

## Apprentissage des refus

Le site ajuste sa sélection à partir des annonces que vous écartez.

**Le pont indispensable.** Vos décisions vivent dans le `localStorage` de votre
navigateur ; le collecteur tourne sur GitHub Actions et ne peut pas les lire.
Le bouton **« ⬇ Exporter mes décisions »**, sur la ligne « Mon statut »,
produit un fichier `decisions.json` à déposer dans `data/`. Il ne contient que
des identifiants et des statuts — le texte des annonces est déjà en base.
Le fichier accepte aussi une liste d'exports, le lien pouvant être partagé.

```bash
# après avoir déposé le fichier téléchargé dans data/
python collecteur/genere_site.py    # affiche le rapport d'ajustement
```

**L'annonce est lue en entier, et ses critères sont figés à la collecte.**
`collecteur/criteres.py` extrait de la fiche complète — pendant qu'elle est
déjà téléchargée pour l'examen linguistique — les critères qui caractérisent
le poste : expérience exigée, licences, qualifications de type, certificats,
niveaux de langue, séniorité, contrat, responsabilités, secteur, nature de
l'activité. Le titre et l'extrait de 400 caractères n'en montraient qu'une
vitrine : mesuré sur 18 annonces, les diplômes passent de 2 à 10 détections,
les contrats de 1 à 10, les responsabilités de 3 à 15.

Ce sont les **critères** qui sont stockés, pas le texte brut : 568 annonces de
2 600 caractères pèseraient 1,5 Mo réécrits deux fois par jour dans le dépôt.
`VERSION_ANALYSE_CRITERES` les versionne, comme pour l'analyse linguistique :
l'incrémenter fait relire les annonces analysées par une version antérieure.

**Chaque critère porte sa modalité.** « 1500 heures minimum » et « 1500 heures
appréciées » n'engagent pas de la même façon. Trois modalités : `exigence`,
`atout`, `mention` (le critère est cité sans qu'on sache ce qu'on en attend).
La modalité se lit dans **la phrase** qui porte le critère, pas dans une
fenêtre de caractères : dans « 3000 hours would be a plus. CPL/IR required. »,
la licence se trouve à trente caractères de « plus » et en héritait à tort.

Les valeurs numériques sont regroupées par tranches — `0-500`, `500-1500`,
`1500-3000`, `3000+` heures. Sans cela « 1500 h », « 1800 h » et « 2000 h »
seraient trois critères distincts, chacun trop rare pour qu'un apprentissage y
voie quoi que ce soit.

**Ce qui est déduit.** Aux critères extraits s'ajoutent des traits du titre :
région, appareil, type de poste, marqueurs du profil. Un trait fréquent chez
les annonces refusées et rare ailleurs devient une règle.

**Ni la compagnie ni la source ne sont jamais des motifs.** Écarter une annonce
juge son contenu, pas l'employeur qui la publie ni la bourse d'emploi où elle a
été trouvée : refuser quatre annonces d'un transporteur ne veut pas dire qu'on
refuse ce transporteur, sa cinquième offre peut être exactement le poste
recherché. Cette garantie ne repose pas sur une liste de noms à écarter — une
telle liste ignorerait toujours les petits employeurs, et refuser quatre
annonces de l'« Aéroclub du Pontreau » aurait produit la règle `pontreau` —
mais sur l'inverse : seul le vocabulaire de `THEMES` et les traits structurés
sont appris. Aucun nom propre ne peut devenir un motif, connu ou non.

**Ce qui décide et ce qui alerte sont séparés.** Une liste blanche a un défaut :
un thème qu'elle ignore — des rotations de nuit, un rythme particulier — reste
invisible. `signaux_non_appris` compte donc *tous* les mots surreprésentés chez
vos refus, mais **uniquement pour les afficher** : aucun ne peut créer de règle.
Le rapport dit « le mot *nuit* revient dans 5 de vos 6 refus » ; vous jugez s'il
décrit un poste ou nomme une compagnie, et il rejoint `THEMES` en une ligne.

La dissymétrie est délibérée : une règle qui masque une annonce peut coûter un
poste sans qu'on le sache, elle mérite un vocabulaire contrôlé ; signaler un mot
ne coûte rien. Un nom d'employeur peut apparaître dans cette liste — c'est sans
danger, elle n'agit pas — et il s'y montre rarement, un nom propre ne se
répétant presque jamais d'une annonce à l'autre.

**Deux ensembles distincts, jamais mélangés.** Les critères favorables naissent
des annonces « Candidature envoyée », les défavorables des « Pas intéressé ».
Ils ne se compensent qu'au moment du score final, jamais à la construction. Les
deux versants appliquent **les mêmes seuils** — auparavant une seule candidature
suffisait à installer un critère favorable définitif, exactement le travers
qu'on refuse au versant négatif :

| Origine | Seuil | Conséquence |
| --- | --- | --- |
| Refus | ≥ 3 **et** ≥ 75 % | exclusion automatique, sans confirmation |
| Refus | ≥ 2 **et** ≥ 50 % | pénalité de score (−2) |
| Candidatures | ≥ 3 **et** ≥ 75 % | critère favorable fort (+4) |
| Candidatures | ≥ 2 **et** ≥ 50 % | critère favorable faible (+2) |

Le veto reste distinct des critères favorables : il protège dès la **première**
candidature, alors qu'un critère favorable doit être confirmé. Protéger et
valoriser ne demandent pas la même preuve.

**Trois issues, pas deux.** Chaque annonce est confrontée aux deux ensembles :

| Issue | Condition | Effet |
| --- | --- | --- |
| `ecarter` | porte un motif d'exclusion | masquée |
| `examiner` | score ≤ −4 par cumul de pénalités | **affichée**, signalée « ⚠ À examiner » |
| `conserver` | sinon | affichée, triée par score |

La deuxième existe pour ne pas trancher sur un faisceau d'indices encore mince.
La fiche affiche ses critères favorables en vert et défavorables en rouge, à
côté des marqueurs du profil en jaune.

**Trois garde-fous contre le surapprentissage.** Sur trois refus, une machine
conclut n'importe quoi : si vos trois premiers rejets sont des postes en
Afrique, elle décide d'exclure l'Afrique, alors que c'était peut-être le type
d'appareil qui déplaisait.

1. *Seuil de présence* — un refus isolé ne fait jamais loi.
2. *Taux de refus* — un trait doit être **rare ailleurs**. « Copilote » figure
   dans presque toutes les annonces, refusées comprises : c'est le métier, pas
   un motif de rejet.
3. *Veto des candidatures* — un trait présent dans une annonce à laquelle vous
   avez postulé ne peut jamais devenir une exclusion, quelle que soit sa
   statistique. Ce que vous avez voulu ne peut pas être ce que vous rejetez.

**L'apprentissage n'observe que le vivier visible.** Mesurer un trait sur la
base entière le diluerait dans 400 articles de presse jamais affichés : « région
Moyen-Orient », refusée huit fois sur huit, semblait n'être refusée qu'une fois
sur dix.

**Le filtrage est silencieux mais pas invisible.** Un dépliant « 🧠 Règles
apprises de vos refus » liste chaque règle active, le nombre d'annonces qu'elle
masque et la statistique qui l'a produite. Une règle tirée de quelques clics
peut se tromper ; on ne la corrige que si l'on sait qu'elle existe. Les seuils
se règlent en tête d'`apprentissage.py`.

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
