"""Serve a local, read-only gallery for the production monthly content calendar."""

from __future__ import annotations

import argparse
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote
from urllib.request import urlopen


DEFAULT_BASE_URL = "https://jubilant-harmony-production-5bd1.up.railway.app"


def _calendar(base_url: str, token: str) -> dict:
    url = f"{base_url.rstrip('/')}/monthly-content?token={quote(token)}&detail=true"
    with urlopen(url, timeout=60) as response:
        return json.load(response)


def _text(value: object) -> str:
    return html.escape(str(value or ""))


def _post_card(entry: dict, index: int) -> str:
    package = entry.get("package") if isinstance(entry.get("package"), dict) else {}
    posts = package.get("platform_posts") if isinstance(package.get("platform_posts"), dict) else {}
    assets = package.get("carousel_assets") if isinstance(package.get("carousel_assets"), list) else []
    if not assets:
        assets = [{"public_url": package.get("primary_publish_image_url", ""), "role": "image"}]
    slides = "".join(
        f'<figure><img src="{_text(asset.get("public_url"))}" alt="{_text(asset.get("role") or "Post image")}" loading="lazy">'
        f'<figcaption>{slide_index}/{len(assets)} · {_text(asset.get("role") or "image")}</figcaption></figure>'
        for slide_index, asset in enumerate(assets, start=1)
        if isinstance(asset, dict) and asset.get("public_url")
    )
    captions = "".join(
        f'<section class="caption" data-platform="{platform}"><h3>{platform.title()}</h3>'
        f'<div class="copy">{_text((posts.get(platform) or {}).get("final_caption")).replace(chr(10), "<br>")}</div></section>'
        for platform in ("facebook", "instagram", "linkedin")
    )
    return f"""
    <article class="post" data-format="{_text(entry.get('format'))}" data-index="{index}">
      <header>
        <div><span class="number">{index:02d}</span><span class="date">{_text(entry.get('date'))} · 17:00 UTC</span></div>
        <span class="format">{_text(entry.get('format'))}</span>
      </header>
      <h2>{_text(entry.get('statement'))}</h2>
      <div class="slides">{slides}</div>
      <div class="captions">{captions}</div>
    </article>"""


def render(calendar: dict) -> bytes:
    entries = calendar.get("entries") if isinstance(calendar.get("entries"), list) else []
    cards = "".join(_post_card(entry, index) for index, entry in enumerate(entries, start=1) if isinstance(entry, dict))
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Infenergy Monthly Post Review</title>
<style>
:root{{--ink:#17242a;--paper:#f4f1e9;--panel:#fff;--accent:#e45b3a;--line:#d8d4ca;--muted:#68747a}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(135deg,#eef4f3 0,#f4f1e9 44%,#f7efe8 100%);color:var(--ink);font-family:Georgia,'Times New Roman',serif}}
.top{{position:sticky;top:0;z-index:5;background:rgba(244,241,233,.96);border-bottom:1px solid var(--line);padding:18px 28px;backdrop-filter:blur(12px)}}
.topline{{max-width:1500px;margin:auto;display:flex;align-items:end;justify-content:space-between;gap:20px}} h1{{font-size:28px;margin:0}} .summary{{color:var(--muted);font:14px 'Segoe UI',sans-serif;margin-top:5px}}
.controls{{display:flex;gap:8px;flex-wrap:wrap}} button{{border:1px solid var(--line);background:var(--panel);padding:9px 13px;cursor:pointer;font:600 13px 'Segoe UI',sans-serif}} button.active{{background:var(--ink);color:#fff;border-color:var(--ink)}}
main{{max-width:1500px;margin:26px auto;padding:0 28px 70px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}}
.post{{background:var(--panel);border:1px solid var(--line);padding:20px;box-shadow:0 8px 24px rgba(23,36,42,.06)}} .post header{{display:flex;justify-content:space-between;align-items:center;font:13px 'Segoe UI',sans-serif;text-transform:uppercase}}
.number{{display:inline-grid;place-items:center;width:34px;height:34px;background:var(--accent);color:#fff;font-weight:800;margin-right:12px}} .date{{font-weight:700}} .format{{color:var(--muted)}} h2{{font-size:25px;line-height:1.18;margin:18px 0}}
.slides{{display:flex;overflow-x:auto;gap:10px;scroll-snap-type:x mandatory;padding-bottom:6px}} figure{{margin:0;min-width:calc(50% - 5px);scroll-snap-align:start}} figure img{{display:block;width:100%;aspect-ratio:1;object-fit:cover;background:#edf0ee}} figcaption{{font:12px 'Segoe UI',sans-serif;color:var(--muted);margin-top:5px;text-transform:uppercase}}
.captions{{margin-top:16px}} .caption h3{{font:700 13px 'Segoe UI',sans-serif;text-transform:uppercase;color:var(--accent);margin:0 0 8px}} .copy{{font:15px/1.5 'Segoe UI',sans-serif;white-space:normal}} .caption:not([data-platform=facebook]){{display:none}}
.empty{{display:none;max-width:1500px;margin:70px auto;text-align:center;color:var(--muted)}}
@media(max-width:900px){{.topline{{align-items:start;flex-direction:column}} main{{grid-template-columns:1fr;padding:0 14px}} .top{{padding:16px 14px}} figure{{min-width:85%}}}}
</style></head><body>
<div class="top"><div class="topline"><div><h1>Monthly Post Review</h1><div class="summary">{len(entries)} saved posts · {_text(calendar.get('start_date'))} to {_text(calendar.get('end_date'))} · read only</div></div>
<div class="controls"><button class="active" data-platform="facebook">Facebook</button><button data-platform="instagram">Instagram</button><button data-platform="linkedin">LinkedIn</button><button class="active" data-format="all">All</button><button data-format="single">Singles</button><button data-format="carousel">Carousels</button></div></div></div>
<main>{cards}</main><div class="empty">No posts match this view.</div>
<script>
let platform='facebook',format='all';
document.querySelectorAll('[data-platform]').forEach(button=>button.addEventListener('click',()=>{{platform=button.dataset.platform;document.querySelectorAll('button[data-platform]').forEach(item=>item.classList.toggle('active',item===button));document.querySelectorAll('.caption').forEach(item=>item.style.display=item.dataset.platform===platform?'block':'none')}}));
document.querySelectorAll('button[data-format]').forEach(button=>button.addEventListener('click',()=>{{format=button.dataset.format;document.querySelectorAll('button[data-format]').forEach(item=>item.classList.toggle('active',item===button));let visible=0;document.querySelectorAll('.post').forEach(item=>{{const show=format==='all'||item.dataset.format===format;item.style.display=show?'block':'none';if(show)visible++}});document.querySelector('.empty').style.display=visible?'none':'block'}}));
</script></body></html>"""
    return page.encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--base-url", default=os.environ.get("INFENERGY_BASE_URL", DEFAULT_BASE_URL))
    args = parser.parse_args()
    token = os.environ.get("MANUAL_RUN_TOKEN", "").strip()
    if not token:
        raise SystemExit("MANUAL_RUN_TOKEN is required")
    page = render(_calendar(args.base_url, token))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format: str, *args: object) -> None:
            return

    print(f"Monthly review: http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()