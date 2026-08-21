# Changelog

Versionnage semantique (`MAJOR.MINOR.PATCH`), applique a partir de `1.0.0` :

- **MAJOR** : changement de comportement significatif (nouvelle capacite majeure du
  pipeline, changement qui affecte des runs existants -- ex. le cache incremental
  change ce qui est reellement execute a chaque `build`). Decision au cas par cas,
  pas une regle stricte de compatibilite d'API (cortex est un outil CLI, pas une
  librairie consommee par du code tiers).
- **MINOR** : nouvelle fonctionnalite retrocompatible (ex. un nouveau flag, une
  nouvelle commande) qui ne change pas le comportement des usages existants.
- **PATCH** : correction de bug, sans nouveau comportement.

Cette version affichee par `cortex --version` (`__version__` dans `src/cortex/__init__.py`,
tenu en phase avec `pyproject.toml`) est independante du mecanisme de mise a jour :
`cortex` n'est pas publie sur PyPI, `cortex update` suit toujours le dernier commit de
`main` quel que soit le numero de version -- voir le README, section « Staying up to
date ». Le numero de version documente ici sert a communiquer l'ampleur d'un
changement, pas a piloter l'installation.

## [2.0.0] - 2026-08-21

### Modifie
- Plafonds `max_tokens` releves pour tous les appels LLM du pipeline : 2048 -> 8192
  pour le triage (`triage/llm_judge.py`), 4096 -> 8192 pour la generation de note et
  la passe de liaison (`vault/generator.py`). Necessaire pour les providers
  `openai-compatible` pointant vers un modele "raisonneur" local (ex. Qwen3 via
  llama.cpp) : le raisonnement interne du modele consomme le meme budget de tokens
  que la reponse finale, et l'ancien plafond risquait de tronquer la reponse avant
  le JSON attendu -- un lot de triage entier retombait alors silencieusement sur
  "keep" par defaut, ou une note generee retombait sur le contenu brut du fichier
  source au lieu d'une note curee. Change reellement ce qui est execute/produit a
  chaque `build`/`triage`/`vault` pour ces providers, d'ou le major : cout et
  latence par appel plus eleves (sans effet sur `anthropic`/`claude-cli`, ou ce
  plafond n'est qu'un plafond jamais atteint en pratique).

## [1.2.0] - 2026-08-10

### Ajoute
- `cortex` lance desormais une session interactive (REPL) quand il est invoque sans
  sous-commande, a la maniere de `claude` : banniere ASCII, invite `cortex>`, et
  acces direct aux commandes existantes (`build`, `triage`, `vault`, `graph`,
  `query`, `update`) depuis la session, sans avoir a retaper `cortex` a chaque ligne.
- Nouvelles commandes slash a l'interieur de la session : `/provider`, `/model`,
  `/effort` (menus interactifs a fleches, via la nouvelle dependance
  `questionary`) pour changer respectivement le provider LLM, le(s) modele(s) et
  le niveau d'effort de raisonnement sans relancer `cortex` ; `/exclude` pour
  gerer les motifs d'exclusion par defaut de la session ; `/config` pour afficher
  la configuration resolue de la session en cours ; `/clear`, `/help`,
  `/exit`/`/quit`.
- Les reglages choisis via ces menus ne s'appliquent qu'a la session REPL en
  cours (ils ne sont pas ecrits dans `config.toml`) ; ils sont prioritaires sur
  les variables d'environnement et le fichier de config pour les commandes
  lancees depuis cette session -- exactement comme un flag `--provider` /
  `--model` / `--effort` passe en ligne de commande.

### Modifie
- Invoquer `cortex` sans arguments n'affiche plus l'aide (`cortex --help` reste
  le moyen documente d'obtenir l'aide) : ce comportement est remplace par le
  lancement de la session interactive decrite ci-dessus.

## [1.1.1] - 2026-08-10

### Ajoute
- `--exclude` accepte desormais plusieurs valeurs separees par des espaces en une
  seule occurrence de la flag (ex. `--exclude .gitignore dataset.csv instructions
  instructions.md`), en plus de la syntaxe repetee existante (`--exclude a --exclude
  b`). Les deux formes sont equivalentes et peuvent etre melangees.

## [1.1.0] - 2026-08-09

### Corrige
- `cortex build`/`vault` : le cache disque (`.cortex/triage-cache.json`,
  `vault-cache.json`) n'etait ecrit qu'une seule fois, tout a la fin d'un run
  entierement reussi. Si le pipeline levait une exception en cours de route (ex. le
  provider `claude-cli` qui epuise ses 4 tentatives apres avoir tape la limite
  d'usage de l'abonnement Claude), tout le travail deja fait dans ce run -- notes deja
  generees, decisions de triage deja rendues -- etait perdu : rien n'atteignait le
  disque. Un `cortex build` relance repartait alors de zero et refaisait les memes
  appels LLM deja payes, jusqu'a retomber sur la meme limite. `cache.save()` est
  desormais dans un `finally` qui couvre tout le corps de `build()`, donc la
  progression realisee avant un crash est toujours persistee et reutilisee au
  prochain lancement.
- `cortex build`/`vault` (CLI) : cette meme exception (`RuntimeError` du provider
  `claude-cli`) n'etait pas interceptee et remontait comme un traceback brut au lieu
  d'un message d'erreur propre.

## [1.0.0] - 2026-08-07

Premiere version numerotee. Etablit le schema de version ci-dessus ; les deux entrees
precedentes sont documentees ici retroactivement pour l'historique, sans numero propre.

### Ajoute
- `--exclude` (repetable) sur `build`/`vault`/`triage` : exclut un fichier/dossier du
  scan par nom exact de composant de chemin ou motif glob (ex. `--exclude data
  --exclude "*.csv"`), avant meme l'heuristique -- utile pour ecarter des secrets
  (cles API) ou de gros volumes de donnees brutes que le triage heuristique ne
  filtrerait pas forcement lui-meme.
- `--effort` / `--triage-effort` / `--vault-effort` (+ variables d'env
  `CORTEX_EFFORT`/`CORTEX_TRIAGE_EFFORT`/`CORTEX_VAULT_EFFORT`, cles config.toml
  correspondantes) : controle le niveau d'effort de raisonnement Claude
  (`low`/`medium`/`high`/`xhigh`/`max`, `output_config.effort` de l'API Anthropic)
  independamment pour le triage et la generation du vault. Provider `anthropic`
  uniquement ; accepte et ignore par `claude-cli`/`openai-compatible` pour garder une
  signature de provider uniforme.
- Ce fichier `CHANGELOG.md`.

### Corrige (a l'origine sans version dediee)
- **Auto-update** : ne s'applique plus automatiquement a chaque invocation (
  `_maybe_auto_update` ne fait plus que notifier). L'ancien comportement relancait
  `uv tool install --force`/equivalent depuis le processus cortex en cours
  d'execution, qui verrouille ses propres fichiers sur Windows -- echec
  systematique (`Access is denied`) laissant parfois l'installation a moitie
  supprimee. `cortex update` reste le moyen explicite d'appliquer une mise a jour.

### Ajoute (a l'origine sans version dediee)
- **Cache incremental `.cortex/`** (`triage-cache.json`, `vault-cache.json`,
  `graphify-cache.json` dans le dossier `--output`) : un fichier source dont le hash
  n'a pas change depuis le dernier `build`/`vault` reutilise sa decision de triage et
  sa note deja generee sans rappeler le LLM ; si rien n'a change dans la composition
  du vault, la passe de liaison et le rebuild Graphify sont sautes entierement.
