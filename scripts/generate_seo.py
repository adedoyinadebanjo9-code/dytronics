#!/usr/bin/env python3
"""Generate crawlable static pages for DYTRONICS from the Supabase catalogue.

Writes (all deterministic, so unchanged data => no git diff):
  p/<slug>/index.html   one real HTML page per active product
  products/index.html   a plain list of every product, grouped by category
  sitemap.xml           every public URL
  seo-slugs.json        product id -> slug, so URLs never change when a name is edited

Safety: if Supabase is unreachable or returns zero products, the script exits
with an error and touches NOTHING, so an outage can never wipe the pages.
Standard library only (no pip install).
"""
import html
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

SITE = "https://www.dytronics.name.ng"
# Publishable (public) key: the same one already shipped in index.html. RLS limits it to active rows.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://oqlbtbdmobhgxpqbyaeq.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_wS7kpnC5GOcHNkgEhbp1eQ_ND2DxAnN")
WHATSAPP = "2347054378193"
ROOT = Path(__file__).resolve().parent.parent
MARKER = "<!-- generated:dytronics-seo - do not edit by hand -->"
DELIVERY = ("Lagos: door delivery, usually within 1-3 days of order confirmation. "
            "Nationwide: delivered via courier partners, typically 3-5 working days.")
RETURNS = ("Components are tested before dispatch. If an item arrives faulty, DOA, or doesn't match "
           "what was agreed, message us within 48 hours of delivery and we'll repair, replace or refund it.")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased;line-height:1.6}
a{color:inherit}
.bar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 5vw;background:var(--green-deep);color:#f4f6f9}
.bar a{text-decoration:none}
.wordmark{font-family:'Fraunces',serif;font-weight:500;letter-spacing:.14em;font-size:15px}
.bar nav{display:flex;gap:18px;font-size:12px;letter-spacing:.08em;text-transform:uppercase}
main{max-width:1000px;margin:0 auto;padding:28px 5vw 56px}
.crumbs{font-size:12px;color:var(--ink-soft);margin-bottom:22px}
.crumbs a{text-decoration:underline}
.product{display:grid;grid-template-columns:1fr 1fr;gap:36px;align-items:start}
@media(max-width:760px){.product{grid-template-columns:1fr}}
.media{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;overflow:hidden}
.media img{width:100%;height:100%;object-fit:contain;display:block}
.eyebrow{font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--green);font-weight:600}
h1{font-family:'Fraunces',serif;font-weight:500;font-size:clamp(26px,4vw,38px);line-height:1.15;margin:8px 0 14px}
.price{font-size:24px;font-weight:600;margin-bottom:4px}
.stock{font-size:13px;color:var(--ink-soft);margin-bottom:20px}
.cta{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:26px}
.btn{display:inline-block;padding:13px 20px;border:1px solid var(--ink);border-radius:var(--radius);font-size:12px;letter-spacing:.1em;text-transform:uppercase;text-decoration:none;font-weight:600}
.btn-solid{background:var(--green);border-color:var(--green);color:#fff}
.btn-solid:hover{background:var(--green-deep)}
.btn:focus-visible,a:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
h2{font-family:'Fraunces',serif;font-weight:500;font-size:18px;margin:22px 0 8px}
p{margin-bottom:10px;color:var(--ink-soft);font-size:15px}
.list{list-style:none}
.list li{border-bottom:1px solid var(--line)}
.list a{display:flex;align-items:center;gap:14px;padding:12px 0;text-decoration:none}
.list img{width:52px;height:52px;object-fit:contain;background:var(--card);border:1px solid var(--line)}
.list .n{flex:1;font-weight:500}
.list .p{color:var(--ink-soft);font-size:14px;white-space:nowrap}
footer{border-top:1px solid var(--line);padding:22px 5vw;font-size:12px;color:var(--ink-soft);text-align:center}
"""

HEAD_COMMON = (
    '<meta charset="UTF-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '<link rel="icon" href="/favicon.ico" sizes="any">\n'
    '<link rel="icon" type="image/svg+xml" href="/favicon.svg">\n'
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n'
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">\n'
    '<link rel="stylesheet" href="/tokens.css">'
)


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def fetch(path, retries=3):
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}",
                                 headers={"apikey": SUPABASE_KEY, "Accept": "application/json"})
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # network, HTTP, JSON
            last = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"Supabase request failed ({path}): {last}")


def slugify(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:80].strip("-")
    return t or "product"


def assign_slugs(products, existing):
    """Keep every slug ever issued (stable URLs even after a rename); only new ids get new slugs."""
    slugs = dict(existing)
    taken = set(slugs.values())
    for p in sorted(products, key=lambda x: (x.get("created_at") or "", x["id"])):
        if p["id"] in slugs:
            continue
        base = slugify(p["name"])
        slug = base if base not in taken else f"{base}-{p['id'][:6]}"
        n = 2
        while slug in taken:
            slug = f"{base}-{p['id'][:6]}-{n}"
            n += 1
        slugs[p["id"]] = slug
        taken.add(slug)
    return slugs


def clean(text):
    t = re.sub(r"\*\*|__|`", "", text or "")
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()


def paragraphs(text):
    return [c for c in (clean(line) for line in (text or "").splitlines()) if c]


def truncate(text, n):
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",.;:- ") + "\u2026"


def price_num(p):
    v = p.get("price")
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def ngn(n):
    return "\u20a6" + f"{int(round(n)):,}"


def in_stock(p):
    s = p.get("stock")
    return s is None or int(s) > 0  # null stock = untracked, treated as available (same as the storefront)


def abs_image(p):
    u = (p.get("image_url") or "").strip()
    return u if u.startswith("https://") else None


def jsonld(obj):
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
            + "</script>")


def page(head_title, desc, canonical, og_type, image, jsonlds, body, extra_head=""):
    og_image = image or f"{SITE}/apple-touch-icon.png"
    card = "summary_large_image" if image else "summary"
    tags = [
        f"<title>{e(head_title)}</title>",
        f'<meta name="description" content="{e(desc)}">',
        f'<link rel="canonical" href="{e(canonical)}">',
        '<meta property="og:site_name" content="DYTRONICS">',
        f'<meta property="og:type" content="{og_type}">',
        f'<meta property="og:title" content="{e(head_title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:url" content="{e(canonical)}">',
        f'<meta property="og:image" content="{e(og_image)}">',
        f'<meta name="twitter:card" content="{card}">',
        f'<meta name="twitter:title" content="{e(head_title)}">',
        f'<meta name="twitter:description" content="{e(desc)}">',
        f'<meta name="twitter:image" content="{e(og_image)}">',
    ]
    head = "\n".join(tags) + "\n" + extra_head + "\n".join(jsonlds)
    return (f'<!DOCTYPE html>\n{MARKER}\n<html lang="en">\n<head>\n{HEAD_COMMON}\n{head}\n'
            f'<style>{CSS}</style>\n</head>\n<body>\n'
            '<header class="bar"><a class="wordmark" href="/">DYTRONICS</a>'
            '<nav><a href="/#shop">Shop</a><a href="/products/">All products</a></nav></header>\n'
            f'{body}\n'
            '<footer>\u00a9 2026 DYTRONICS \u00b7 Lagos, Nigeria \u00b7 <a href="/privacy.html">Privacy</a> \u00b7 '
            '<a href="/terms.html">Terms</a></footer>\n</body>\n</html>\n')


def whatsapp_link(p):
    pn = price_num(p)
    price_text = f"({ngn(pn)})" if pn else "(price on request)"
    msg = (f"Hi DYTRONICS, I'm interested in the {p['name']} {price_text}. "
           "I'd like to know availability and delivery options.")
    return f"https://wa.me/{WHATSAPP}?text=" + urllib.parse.quote(msg, safe="")


def product_page(p, slug, cat_label):
    url = f"{SITE}/p/{slug}/"
    pn = price_num(p)
    ok = in_stock(p)
    desc_paras = paragraphs(p.get("description"))
    spec_paras = paragraphs(p.get("spec_notes"))
    desc_flat = " ".join(desc_paras)
    spec_flat = " ".join(spec_paras)
    show_specs = bool(spec_flat) and spec_flat not in desc_flat and desc_flat not in spec_flat
    seed = desc_flat or spec_flat
    meta_desc = truncate(seed, 155) if seed else \
        f"Buy {p['name']} from DYTRONICS, a Lagos electronics parts shop with nationwide delivery."
    title = f"{p['name']} - {ngn(pn)} | DYTRONICS" if pn else f"{p['name']} | DYTRONICS"
    image = abs_image(p)

    product_ld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"],
                  "description": truncate(seed, 500) if seed else meta_desc, "url": url}
    if image:
        product_ld["image"] = [image]
    if cat_label:
        product_ld["category"] = cat_label
    if pn:
        product_ld["offers"] = {
            "@type": "Offer", "url": url, "priceCurrency": "NGN", "price": pn,
            "itemCondition": "https://schema.org/NewCondition",
            "availability": "https://schema.org/InStock" if ok else "https://schema.org/OutOfStock",
            "seller": {"@type": "Organization", "name": "DYTRONICS"}}
    crumbs_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "All products", "item": SITE + "/products/"},
        {"@type": "ListItem", "position": 3, "name": p["name"], "item": url}]}

    media = (f'<img src="{e(image)}" alt="{e(p["name"])}" width="600" height="600">' if image
             else '<span class="eyebrow">DYTRONICS</span>')
    price_html = (f'<div class="price">{e(ngn(pn))}</div>' if pn
                  else '<div class="price">Message us for pricing</div>')
    stock_html = f'<div class="stock">{"In stock" if ok else "Currently out of stock"}</div>'
    desc_html = ("<h2>Description</h2>" + "".join(f"<p>{e(x)}</p>" for x in desc_paras)) if desc_paras else ""
    spec_html = ("<h2>Specs</h2>" + "".join(f"<p>{e(x)}</p>" for x in spec_paras)) if show_specs else ""
    body = (f'<main>\n<div class="crumbs"><a href="/">Home</a> / <a href="/products/">All products</a>'
            + (f' / {e(cat_label)}' if cat_label else "") + f' / {e(p["name"])}</div>\n'
            f'<div class="product">\n<div class="media">{media}</div>\n<div>\n'
            + (f'<span class="eyebrow">{e(cat_label)}</span>\n' if cat_label else "")
            + f'<h1>{e(p["name"])}</h1>\n{price_html}\n{stock_html}\n'
            f'<div class="cta"><a class="btn btn-solid" href="{e(whatsapp_link(p))}" rel="noopener">Order on WhatsApp</a>'
            '<a class="btn" href="/#shop">View in shop</a></div>\n'
            f'{desc_html}{spec_html}<h2>Delivery</h2><p>{e(DELIVERY)}</p>'
            f'<h2>Returns</h2><p>{e(RETURNS)}</p>\n</div>\n</div>\n</main>')
    return page(title, meta_desc, url, "product", image, [jsonld(product_ld), jsonld(crumbs_ld)], body)


def index_page(products, slugs, cat_labels):
    url = f"{SITE}/products/"
    groups = {}
    for p in products:
        groups.setdefault(p.get("category") or "", []).append(p)
    order = [c for c in cat_labels if c in groups] + sorted(c for c in groups if c not in cat_labels)
    sections = []
    for c in order:
        label = cat_labels.get(c) or (c.replace("-", " ").title() if c else "Other")
        items = []
        for p in groups[c]:
            pn = price_num(p)
            img = abs_image(p)
            thumb = f'<img src="{e(img)}" alt="" width="52" height="52" loading="lazy">' if img else ""
            items.append(f'<li><a href="/p/{e(slugs[p["id"]])}/">{thumb}<span class="n">{e(p["name"])}</span>'
                         f'<span class="p">{e(ngn(pn)) if pn else "Ask for price"}</span></a></li>')
        sections.append(f"<h2>{e(label)}</h2>\n<ul class=\"list\">\n" + "\n".join(items) + "\n</ul>")
    desc = (f"Browse all {len(products)} electronic components, tools and repair parts at DYTRONICS. "
            "Genuine parts, same-day dispatch in Lagos, nationwide shipping.")
    ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "All products", "item": url}]}
    body = ('<main>\n<div class="crumbs"><a href="/">Home</a> / All products</div>\n'
            '<h1>All products</h1>\n<p>Electronic components, tools and repair parts from DYTRONICS, Lagos.</p>\n'
            + "\n".join(sections) + "\n</main>")
    return page("All Electronic Components & Repair Parts | DYTRONICS", desc, url, "website", None, [jsonld(ld)], body)


def sitemap(products, slugs):
    urls = [SITE + "/", SITE + "/products/"] + [f"{SITE}/p/{slugs[p['id']]}/" for p in products] \
        + [SITE + "/privacy.html", SITE + "/terms.html"]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"  <url><loc>{e(u)}</loc></url>\n" for u in urls) + "</urlset>\n")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\r\n", "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def self_check(path, text):
    for needle, want in (("<title>", 1), ('rel="canonical"', 1), ("<h1", 1)):
        if text.count(needle) != want:
            raise AssertionError(f"{path}: expected {want} x {needle!r}, found {text.count(needle)}")


def main():
    products = fetch("dytronics_products?select=id,name,category,price,stock,description,spec_notes,image_url,created_at"
                     "&active=eq.true&order=sort_order.asc,created_at.asc,id.asc")
    categories = fetch("dytronics_categories?select=slug,label&active=eq.true&order=sort_order.asc")
    if not isinstance(products, list) or not products:
        print("ABORT: no active products returned; leaving existing pages untouched.", file=sys.stderr)
        return 1
    cat_labels = {c["slug"]: c["label"] for c in categories}

    slug_file = ROOT / "seo-slugs.json"
    existing = json.loads(slug_file.read_text("utf-8")) if slug_file.exists() else {}
    slugs = assign_slugs(products, existing)

    outputs = {}
    for p in products:
        outputs[ROOT / "p" / slugs[p["id"]] / "index.html"] = product_page(p, slugs[p["id"]], cat_labels.get(p.get("category")))
    outputs[ROOT / "products" / "index.html"] = index_page(products, slugs, cat_labels)
    for path, text in outputs.items():
        self_check(path, text)  # fail BEFORE writing anything

    for path, text in outputs.items():
        write(path, text)
    write(ROOT / "sitemap.xml", sitemap(products, slugs))
    write(slug_file, json.dumps(dict(sorted(slugs.items())), indent=2) + "\n")

    live = {slugs[p["id"]] for p in products}
    removed = 0
    pdir = ROOT / "p"
    for d in pdir.iterdir() if pdir.exists() else []:
        idx = d / "index.html"
        if d.is_dir() and d.name not in live and idx.exists() and MARKER in idx.read_text("utf-8"):
            shutil.rmtree(d)
            removed += 1
    print(f"OK: {len(products)} product pages, {len(categories)} categories, {removed} stale pages removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
