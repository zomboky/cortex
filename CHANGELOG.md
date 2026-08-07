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
