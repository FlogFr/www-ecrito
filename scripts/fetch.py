# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4", "pyyaml"]
# ///
"""Récupère tout le contenu de l'ancien site Wagtail (https://ecrito.fr) et
l'écrit sous forme de fichiers Markdown dans content/posts/<slug>/.

    uv run scripts/fetch.py            # textes + photos
    uv run scripts/fetch.py --no-photos

Le script est idempotent : les photos déjà téléchargées ne le sont pas de nouveau.
"""

import argparse
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import yaml
from bs4 import BeautifulSoup, NavigableString, Tag

SITE = "https://ecrito.fr"
S3 = "https://ecrito.s3.fr-par.scw.cloud/ecrito/static"
ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "content" / "posts"

# Pays de chaque étape (le site d'origine ne stockait pas cette information).
COUNTRIES = [
    ("France", ["2024-01-07-decollage"]),
    ("Corée du Sud", ["seoul"]),
    ("Cambodge", ["angkor", "koh-ta-kiev", "kampot", "kampong-cham", "ratanakiri"]),
    ("Laos", ["4000-islands", "pakse", "thakheh", "vang-vieng", "nong-khiaw"]),
    ("Chine", ["kunming", "lijiang", "jianshui"]),
    ("Vietnam", ["vietnam", "yen-bai", "hanoi", "than-hoa", "cat-ba", "ninh-binh",
                 "hoi-an", "dalat", "ho-chi-minh", "mekong", "cat-tien"]),
    ("Malaisie", ["malaisie", "penang", "langkawi", "taman-negara", "cherating",
                  "ile-paradisiaque", "mallacca"]),
    ("Indonésie", ["sumatra", "krui", "jakarta"]),
    ("Thaïlande", [""]),  # tout le reste
]

# Corrections des données d'origine, appliquées lors de l'import.
FIXES = {
    # Date saisie 2024-04-28 par erreur : l'étape se situe entre Koh Ta Kiev et Kampong Cham.
    "2024-04-28-kampot": {"date": "2024-03-28"},
    # Le pin d'origine pointait vers la Thaïlande ; le parc de Cat Tien est au Vietnam.
    "2024-08-07-cat-tien-et-decollage": {"lat": 11.4234, "lon": 107.4278},
}

# Libellé court affiché sur la carte quand le titre est trop long.
LABELS = {
    "2024-04-27-un-peu-de-luxe-et-repos-avang-vieng-et-luang-prabang": "Vang Vieng & Luang Prabang",
    "2024-09-24-arrivee-a-sumatra-avec-dumai-bukittinggi-bengkulu": "Sumatra",
    "2024-02-02-koh-chang-2e-plus-grande-ile-de-thailande": "Koh Chang",
    "2024-09-21-mallacca-derniere-destination-de-la-malaisie": "Mallacca",
    "2024-09-10-la-cote-est-avec-cherating-terrenganu": "Cherating & Terengganu",
    "2024-04-02-kampong-cham-kratie-et-anecdotes": "Kampong Cham & Kratie",
}

BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "img", "iframe", "ul", "ol"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ecrito-static-export"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(get(url).decode("utf-8"), "html.parser")


def country_for(slug: str) -> str:
    for country, keys in COUNTRIES:
        if any(k in slug for k in keys):
            return country
    raise AssertionError(slug)


# --- Conversion HTML (rich text Wagtail) -> Markdown -------------------------

def md_escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("*", "\\*").replace("`", "\\`")
    return re.sub(r"^(\s*)([#>+\-]|\d+\.)(\s)", r"\1\\\2\3", text)


def inline(node) -> str:
    out = []
    for child in node.children:
        if isinstance(child, NavigableString):
            out.append(md_escape(re.sub(r"\s+", " ", str(child))))
        elif child.name in ("b", "strong"):
            inner = inline(child).strip()
            out.append(f"**{inner}**" if inner else "")
        elif child.name in ("i", "em"):
            inner = inline(child).strip()
            out.append(f"*{inner}*" if inner else "")
        elif child.name == "a":
            out.append(f"[{inline(child).strip()}]({child.get('href', '')})")
        elif child.name == "br":
            out.append("  \n")
        else:
            out.append(inline(child))
    return "".join(out)


def photo_urls(src: str) -> list[str]:
    """URLs candidates pour une image : l'original public d'abord, puis la
    rendition Wagtail, et en dernier recours l'URL signée (valable 1 h) de la page."""
    path = urlparse(src).path
    name = path.rsplit("/", 1)[-1]
    if "/original_images/" in path:
        return [f"{S3}/original_images/{name}", src]
    base = re.sub(r"\.(width|height|max|min|fill|scale|original)-[^.]+(?=\.\w+$)", "", name)
    return [f"{S3}/original_images/{base}", f"{S3}/images/{name}", src]


class Converter:
    def __init__(self):
        self.blocks: list[str] = []
        self.photos: dict[str, list[str]] = {}  # nom local -> URLs candidates
        self.buffer: list[str] = []

    def flush(self):
        text = "".join(self.buffer).strip()
        if text:
            self.blocks.append(text)
        self.buffer = []

    def photo(self, src: str) -> str:
        urls = photo_urls(src)
        name = urls[0].rsplit("/", 1)[-1]
        self.photos.setdefault(name, urls)
        return "photos/" + name

    def walk(self, node):
        for child in node.children:
            if isinstance(child, NavigableString):
                self.buffer.append(md_escape(re.sub(r"\s+", " ", str(child))))
                continue
            name = child.name
            if name in ("h1", "h2"):
                self.flush()
                self.blocks.append("## " + inline(child).strip())
            elif name in ("h3", "h4"):
                self.flush()
                self.blocks.append("### " + inline(child).strip())
            elif name == "img":
                self.flush()
                self.blocks.append(f"![{child.get('alt', '')}]({self.photo(child['src'])})")
            elif name == "iframe":
                self.flush()
                m = re.search(r"youtube\.com/embed/([\w-]+)", child.get("src", ""))
                if m:
                    self.blocks.append(f"@[youtube]({m.group(1)})")
            elif name in ("p", "div", "ul", "ol"):
                if child.find(BLOCK_TAGS):
                    self.flush()
                    self.walk(child)
                    self.flush()
                else:
                    self.flush()
                    self.buffer.append(inline(child))
                    self.flush()
            else:
                self.buffer.append(inline(child) if isinstance(child, Tag) else str(child))
        return self


def parse_post(slug: str) -> tuple[dict, str, dict[str, list[str]]]:
    s = soup(f"{SITE}/{slug}/")
    full_title = s.select_one(".card-header h3").get_text(strip=True)
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.*)", full_title)
    date, title = m.groups()

    desc = s.find("meta", attrs={"name": "description"})
    desc = desc["content"].strip() if desc else ""
    if desc in (full_title, slug) or desc.lower().replace(" ", "-") == slug:
        desc = ""

    scripts = " ".join(x.get_text() for x in s.find_all("script"))
    lat, lon = map(float, re.search(r"L\.marker\(\[([-\d.]+),\s*([-\d.]+)\]", scripts).groups())

    body = s.select_one(".card-body")
    conv = Converter()
    for block in body.find_all("div", class_="container", recursive=False):
        conv.walk(block.select_one(".col") or block).flush()

    gallery = []
    for img in body.select(".carousel .carousel-item img"):
        gallery.append(conv.photo(img["src"]))

    fix = FIXES.get(slug, {})
    meta = {
        "title": title,
        "date": fix.get("date", date),
        "country": country_for(slug),
        "location": {"lat": fix.get("lat", lat), "lon": fix.get("lon", lon)},
    }
    if slug in LABELS:
        meta["label"] = LABELS[slug]
    if desc:
        meta["description"] = desc
    meta["gallery"] = gallery

    markdown = "\n\n".join(conv.blocks).strip() + "\n"
    return meta, markdown, conv.photos


def download(urls: list[str], dest: Path) -> str:
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    for url in urls:
        try:
            data = get(url)
            break
        except urllib.error.HTTPError as e:
            error = f"ERREUR {e.code} {url}"
    else:
        return error
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.rename(dest)
    return "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-photos", action="store_true")
    args = parser.parse_args()

    home = soup(SITE + "/")
    slugs = [a["href"].strip("/") for a in home.select(".list-group a")]
    print(f"{len(slugs)} articles trouvés")

    jobs = []
    for slug in slugs:
        meta, markdown, photos = parse_post(slug)
        folder = POSTS / slug
        folder.mkdir(parents=True, exist_ok=True)
        front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000)
        (folder / "index.md").write_text(f"---\n{front}---\n\n{markdown}", encoding="utf-8")
        jobs += [(urls, folder / "photos" / name) for name, urls in photos.items()]
        print(f"  {meta['date']}  {meta['title']}  ({len(photos)} photos)")

    logo = ROOT / "static" / "img" / "logo.png"
    jobs.append(([f"{S3}/images/logo.png"], logo))

    if args.no_photos:
        return
    print(f"Téléchargement de {len(jobs)} fichiers…")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda j: download(*j), jobs))
    errors = [r for r in results if r.startswith("ERREUR")]
    print(f"{results.count('ok')} téléchargés, {results.count('skip')} déjà présents, {len(errors)} erreurs")
    for e in errors:
        print("  " + e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
