# /// script
# requires-python = ">=3.11"
# dependencies = ["jinja2", "markdown", "pillow", "pyyaml"]
# ///
"""Génère le site statique dans dist/ à partir de content/posts/*/index.md.

    uv run scripts/build.py
    python3 -m http.server -d dist 8000   # aperçu local

Les photos originales (content/posts/*/photos/, hors Git) sont redimensionnées en
WebP 600 px et 1600 px dans media/, qui est versionné : sans les originaux (par
exemple sur GitHub Actions), le site est généré à partir de media/.

Variables d'environnement :
    SITE_URL   URL publique du site, pour les liens absolus (https://ecrito.fr)
    BASE_PATH  sous-chemin du site, ex. "/www-ecrito" sur <user>.github.io (vide par défaut)
"""

import hashlib
import html
import json
import math
import os
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "posts"
STATIC = ROOT / "static"
TEMPLATES = ROOT / "templates"
MEDIA = ROOT / "media"
DIST = ROOT / "dist"

SITE_URL = os.environ.get("SITE_URL", "https://ecrito.fr").rstrip("/")
BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")
SIZES = (600, 1600)

COUNTRY_COLORS = {
    "France": "#64748b",
    "Thaïlande": "#e63946",
    "Corée du Sud": "#2563eb",
    "Cambodge": "#7c3aed",
    "Laos": "#f59e0b",
    "Chine": "#db2777",
    "Vietnam": "#059669",
    "Malaisie": "#0891b2",
    "Indonésie": "#ea580c",
}

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre"]


@dataclass
class Photo:
    src: Path    # fichier original (peut être absent)
    media: Path  # dossier des versions WebP
    stem: str    # nom publié, sans extension
    width: int = 0
    height: int = 0

    def url(self, size: int) -> str:
        return f"photos/{self.stem}-{size}.webp"

    @property
    def ratio(self) -> float:
        return self.width / self.height if self.height else 1.5


@dataclass
class Post:
    slug: str
    title: str
    date: date
    country: str
    lat: float
    lon: float
    label: str
    description: str
    markdown: str
    photos: dict[str, Photo] = field(default_factory=dict)  # "photos/x.jpg" -> Photo
    gallery: list[Photo] = field(default_factory=list)
    html: str = ""
    excerpt: str = ""
    index: int = 0

    @property
    def url(self) -> str:
        return f"/{self.slug}/"

    @property
    def cover(self) -> Photo | None:
        if self.gallery:
            return self.gallery[0]
        return next(iter(self.photos.values()), None)

    @property
    def color(self) -> str:
        return COUNTRY_COLORS.get(self.country, "#64748b")


def french_date(d: date) -> str:
    return f"{d.day if d.day > 1 else '1er'} {MONTHS[d.month - 1]} {d.year}"


def haversine(a: Post, b: Post) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


# --- Lecture du contenu -------------------------------------------------------

def load_post(folder: Path) -> Post:
    raw = (folder / "index.md").read_text(encoding="utf-8")
    _, front, body = raw.split("---\n", 2)
    meta = yaml.safe_load(front)
    d = meta["date"]
    post = Post(
        slug=folder.name,
        title=meta["title"],
        date=d if isinstance(d, date) else date.fromisoformat(str(d)),
        country=meta["country"],
        lat=float(meta["location"]["lat"]),
        lon=float(meta["location"]["lon"]),
        label=meta.get("label") or meta["title"],
        description=meta.get("description", ""),
        markdown=body.strip(),
    )
    refs = list(meta.get("gallery") or []) + re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", body)
    for ref in refs:
        if ref in post.photos:
            continue
        photo = Photo(src=folder / ref, media=MEDIA / post.slug, stem=Path(ref).stem)
        if photo.src.exists() or all(photo.media.joinpath(f"{photo.stem}-{s}.webp").exists() for s in SIZES):
            post.photos[ref] = photo
        else:
            print(f"  ! photo absente, ignorée : {photo.src.relative_to(ROOT)}")
    post.gallery = [post.photos[ref] for ref in meta.get("gallery") or [] if ref in post.photos]
    return post


# --- Photos -------------------------------------------------------------------

def process_photo(src: Path, out_dir: Path, stem: str) -> tuple[int, int]:
    """Crée les variantes WebP d'une photo (si besoin) et renvoie la taille de la grande."""
    targets = [out_dir / f"{stem}-{size}.webp" for size in SIZES]
    if not src.exists() or all(t.exists() and t.stat().st_mtime >= src.stat().st_mtime for t in targets):
        with Image.open(targets[-1]) as im:
            return im.size
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.draft("RGB", (SIZES[-1], SIZES[-1]))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        for size, target in zip(SIZES, targets):
            variant = im.copy()
            variant.thumbnail((size, size), Image.Resampling.LANCZOS)
            variant.save(target, "WEBP", quality=80, method=5)
        return variant.size


def process_photos(posts: list[Post]):
    photos = [photo for post in posts for photo in post.photos.values()]
    with ProcessPoolExecutor() as pool:
        sizes = pool.map(process_photo, [p.src for p in photos], [p.media for p in photos],
                         [p.stem for p in photos], chunksize=4)
        for photo, (w, h) in zip(photos, sizes):
            photo.width, photo.height = w, h

    # Supprime de media/ les photos qui ne sont plus utilisées.
    used = {p.media / f"{p.stem}-{size}.webp" for p in photos for size in SIZES}
    for f in MEDIA.rglob("*.webp"):
        if f not in used:
            f.unlink()
    for d in MEDIA.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    print(f"{len(photos)} photos prêtes")


# --- Rendu Markdown -----------------------------------------------------------

YOUTUBE = (
    '<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{id}" '
    'title="Vidéo YouTube" loading="lazy" allow="accelerometer; autoplay; clipboard-write; '
    'encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div>'
)


def figure(photo: Photo, alt: str) -> str:
    # Les alt d'origine sont souvent le nom du fichier : on les ignore.
    alt = "" if re.fullmatch(r"[\w\-. ]*\d{4,}[\w\-. ]*", alt) else alt
    caption = f"<figcaption>{alt}</figcaption>" if alt else ""
    return (
        f'<figure class="figure"><a href="{photo.url(1600)}" data-lightbox>'
        f'<img src="{photo.url(600)}" srcset="{photo.url(600)} 600w, {photo.url(1600)} 1600w" '
        f'sizes="(min-width: 1400px) 760px, (min-width: 960px) 55vw, 100vw" width="{photo.width}" height="{photo.height}" '
        f'alt="{html.escape(alt)}" loading="lazy" decoding="async"></a>{caption}</figure>'
    )


def render_body(post: Post) -> str:
    text = re.sub(r"^@\[youtube\]\(([\w-]+)\)$", lambda m: YOUTUBE.format(id=m.group(1)),
                  post.markdown, flags=re.M)
    out = markdown.markdown(text, extensions=["sane_lists"])

    def img(m):
        alt, ref = html.unescape(m.group(1)), m.group(2)
        return figure(post.photos[ref], alt) if ref in post.photos else ""

    out = re.sub(r'<p><img alt="([^"]*)" src="([^"]+)" ?/?></p>', img, out)
    out = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', out)
    return out


def excerpt(post: Post) -> str:
    if post.description:
        return post.description
    m = re.search(r"<p>(.*?)</p>", post.html, re.S)
    text = re.sub(r"<[^>]+>", "", m.group(1)) if m else ""
    text = html.unescape(text).strip()
    if len(text) > 170:
        text = text[:170].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text


# --- Génération ---------------------------------------------------------------

def file_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:10]


def chapters(posts: list[Post]) -> list[dict]:
    """Regroupe les étapes consécutives d'un même pays."""
    out = []
    for post in posts:
        if not out or out[-1]["country"] != post.country:
            out.append({"country": post.country, "color": post.color, "posts": []})
        out[-1]["posts"].append(post)
    return out


def build():
    posts = sorted((load_post(f) for f in CONTENT.iterdir() if (f / "index.md").exists()),
                   key=lambda p: (p.date, p.slug))
    process_photos(posts)
    for i, post in enumerate(posts):
        post.index = i + 1
        post.html = render_body(post)
        post.excerpt = excerpt(post)

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(STATIC, DIST / "static")
    for post in posts:
        dest = DIST / post.slug / "photos"
        dest.mkdir(parents=True)
        for photo in post.photos.values():
            for size in SIZES:
                name = f"{photo.stem}-{size}.webp"
                os.link(photo.media / name, dest / name)

    # Icônes à partir du logo
    with Image.open(STATIC / "img" / "logo.png") as logo:
        for size, name in ((96, "logo-96.webp"), (64, "favicon.png"), (180, "apple-touch-icon.png")):
            icon = logo.copy()
            icon.thumbnail((size, size), Image.Resampling.LANCZOS)
            icon.save(DIST / "static" / "img" / name)
    (DIST / "static" / "img" / "logo.png").unlink()

    stages = [{
        "n": p.index, "url": BASE_PATH + p.url, "title": p.title, "label": p.label,
        "date": french_date(p.date), "country": p.country,
        "lat": p.lat, "lon": p.lon,
        "cover": f"{BASE_PATH}{p.url}{p.cover.url(600)}" if p.cover else None,
    } for p in posts]
    (DIST / "static" / "js" / "stages.js").write_text(
        "window.ECRITO = " + json.dumps({"stages": stages, "colors": COUNTRY_COLORS},
                                        ensure_ascii=False) + ";\n", encoding="utf-8")

    asia = [p for p in posts if p.country != "France"]
    stats = {
        "stages": len(posts),
        "countries": len({p.country for p in asia}),
        "days": (posts[-1].date - posts[0].date).days,
        "km": round(sum(haversine(a, b) for a, b in zip(posts, posts[1:])), -3),
        "photos": sum(len(p.photos) for p in posts),
        "start": french_date(posts[0].date),
        "end": french_date(posts[-1].date),
    }

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape())
    env.filters["frdate"] = french_date
    env.filters["thousands"] = lambda n: f"{int(n):,}".replace(",", " ")
    env.globals.update(
        site_url=SITE_URL,
        base=BASE_PATH,
        version={p.name: file_hash(p) for p in (DIST / "static").rglob("*.*") if p.suffix in (".css", ".js")},
    )

    def write(path: str, template: str, **ctx):
        dest = DIST / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(template).render(**ctx), encoding="utf-8")

    write("index.html", "index.html", posts=posts, chapters=chapters(posts), stats=stats,
          countries=list(dict.fromkeys((p.country, p.color) for p in asia)))
    for i, post in enumerate(posts):
        write(f"{post.slug}/index.html", "post.html", post=post, total=len(posts),
              prev=posts[i - 1] if i else None, next=posts[i + 1] if i + 1 < len(posts) else None)
    write("404.html", "404.html")
    write("sitemap.xml", "sitemap.xml", posts=posts)
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    print(f"{len(posts)} étapes générées dans {DIST.relative_to(ROOT)}/")


if __name__ == "__main__":
    build()
