# ecrito.fr — carnet de voyage

Site statique du carnet de voyage d'Elisa et Florian en Asie (janvier → octobre 2024).
Remplace l'ancien site Django / Wagtail (toujours disponible dans l'historique Git).

- Page d'accueil : le tracé complet du voyage sur une carte, chaque pin porte le titre
  de l'étape et mène à l'article.
- Article : le texte et les photos à gauche, la carte de l'étape à droite (sous la
  photo de couverture sur mobile).

## Prérequis

[uv](https://docs.astral.sh/uv/) : il installe tout seul les dépendances Python des scripts.

## Générer le site

```bash
uv run scripts/build.py
```

Le site est écrit dans `dist/`. Aperçu local :

```bash
python3 -m http.server -d dist 8000
```

Les URL des articles sont les mêmes que sur l'ancien site.

## Publier sur GitHub Pages

Le workflow `.github/workflows/pages.yml` génère et publie le site à chaque push sur `main`.

1. Sur GitHub : **Settings → Pages → Build and deployment → Source : GitHub Actions**.
2. Poussez sur `main`. Le site est en ligne sur https://flogfr.github.io/www-ecrito/
   (onglet **Actions** pour suivre la publication).

Domaine personnalisé `ecrito.fr` (facultatif) :

1. **Settings → Pages → Custom domain** : `ecrito.fr`.
2. Chez le registrar, remplacez les enregistrements DNS de `ecrito.fr` par :
   - `A` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - `AAAA` → `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`
   - `www` en `CNAME` → `flogfr.github.io`
3. Une fois le DNS propagé, cochez **Enforce HTTPS**, puis relancez le workflow
   (**Actions → Publier sur GitHub Pages → Run workflow**) pour que les liens absolus
   (partage, sitemap) utilisent `https://ecrito.fr`.

Le sous-chemin (`/www-ecrito` ou rien avec le domaine) est géré automatiquement.

## Contenu

Chaque étape est un dossier `content/posts/<slug>/` :

```
index.md     # en-tête YAML (titre, date, pays, coordonnées, galerie) + texte en Markdown
photos/      # photos originales
```

- `location` : coordonnées du pin sur la carte.
- `label` (optionnel) : titre court affiché sur la carte.
- `gallery` : photos affichées sous le texte ; la première sert de couverture.
- `@[youtube](ID)` sur une ligne seule insère une vidéo YouTube.

Les couleurs des pays se règlent dans `COUNTRY_COLORS` (`scripts/build.py`).

## Photos

- `content/posts/<slug>/photos/` : originaux (~1,5 Go), **exclus de Git**. Gardez-en
  une sauvegarde ailleurs : c'est la seule copie une fois le bucket S3 fermé.
- `media/<slug>/` : versions WebP 600 et 1600 px (~150 Mo), **versionnées**. C'est ce
  qu'utilise GitHub Actions pour générer le site.

Pour ajouter une photo : déposez l'original dans `photos/`, référencez-le dans
`index.md`, lancez `uv run scripts/build.py`, puis commitez `media/`.

## Réimporter depuis l'ancien site

```bash
uv run scripts/fetch.py
```

Ce script a servi à récupérer textes, coordonnées et photos depuis https://ecrito.fr.
Il réécrit les `index.md` : ne le relancez pas après avoir modifié le contenu à la main.
Les corrections de données appliquées pendant l'import sont dans `FIXES`.
