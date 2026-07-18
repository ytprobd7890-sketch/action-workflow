#!/usr/bin/env python3
"""PRO PUBLIC VIDEO FETCHER

Batch-extracts public post links and embedded media URLs from a category/label
page. Optional downloads work only for public direct media URLs and supported
embeds. It does not bypass DRM, login, paywalls, CAPTCHAs, or access controls.
Use only for content you own or are authorized to archive.

Install optional downloader: python -m pip install -U yt-dlp
Examples:
  python pro_video_fetcher.py "https://example.com/search/label/series"
  python pro_video_fetcher.py URL --download --workers 3
  python pro_video_fetcher.py URL --json results.json
"""
import argparse, concurrent.futures, html, json, os, re, subprocess, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

UA = "Authorized-ProVideoFetcher/1.0"
MAX = 12 * 1024 * 1024

def get(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=25) as r:
        b = r.read(MAX + 1)
        if len(b) > MAX: raise RuntimeError("response exceeds safety limit")
        return b.decode("utf-8", "replace"), r.geturl()

def clean(s):
    return html.unescape(re.sub(r"\s+", " ", s or "")).strip()

def links_on(index_url, text):
    base = urlparse(index_url)
    out = set()
    for raw in re.findall(r'''(?:href|data-href)\s*=\s*["']([^"']+)''', text, re.I):
        u = urljoin(index_url, html.unescape(raw).replace("&amp;", "&"))
        p = urlparse(u)
        if p.scheme in ("http", "https") and p.netloc == base.netloc:
            if re.search(r"/\d{4}/\d{2}/[^/?#]+\.html(?:$|[?#])", u): out.add(u.split("#")[0])
    return sorted(out)

def inspect_page(url):
    text, final = get(url)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = clean(title_m.group(1)) if title_m else ""
    thumb = None
    for pattern in (
        r'''<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image)["'][^>]+content=["']([^"']+)''',
        r'''<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["'](?:og:image|twitter:image)["']''',
        r'''<img[^>]+(?:src|data-src)=["']([^"']+)''',
    ):
        m = re.search(pattern, text, re.I | re.S)
        if m:
            candidate = html.unescape(m.group(1)).replace("&amp;", "&")
            if candidate.startswith(("http://", "https://", "/")):
                thumb = urljoin(final, candidate)
                break
    frames = [html.unescape(x).replace("&amp;", "&") for x in re.findall(r'''<iframe\b[^>]*?src=["']([^"']+)''', text, re.I)]
    direct = re.findall(r'''https?://[^"'\s<>]+\.(?:mp4|webm|m3u8)(?:\?[^"'\s<>]*)?''', text, re.I)
    embeds = []
    for x in frames:
        if any(k in x.lower() for k in ("blogger.com/video", "rumble.com", "youtube.com", "youtu.be", "vimeo.com")):
            if x not in embeds: embeds.append(x)
    return {"page_url": final, "title": title, "thumbnail": thumb, "direct_urls": list(dict.fromkeys(direct)), "embed_urls": embeds}

def download(url, folder, title, n):
    exe = shutil_which("yt-dlp")
    if not exe: return "yt-dlp not installed"
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-. ]+", "_", title or f"video_{n}")[:100].strip() or f"video_{n}"
    template = str(folder / f"{n:03d} - {safe}.%(ext)s")
    try:
        p = subprocess.run([exe, "--no-playlist", "--no-part", "--restrict-filenames", "-o", template, url], text=True, capture_output=True, timeout=900)
        return "downloaded" if p.returncode == 0 else (p.stderr[-240:].replace("\n", " ") or "download failed")
    except Exception as e: return str(e)

def shutil_which(x):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(d) / x
        if p.is_file() and os.access(p, os.X_OK): return str(p)
    return None

def main():
    ap = argparse.ArgumentParser(description="Batch extract public video links from a category/label page")
    ap.add_argument("url", help="category/label page or individual post URL")
    ap.add_argument("--download", action="store_true", help="download public direct URLs using yt-dlp")
    ap.add_argument("--out", default="downloads", help="download folder")
    ap.add_argument("--workers", type=int, default=3, choices=range(1, 9))
    ap.add_argument("--json", metavar="FILE", help="save results as JSON")
    args = ap.parse_args()
    try: index_text, final = get(args.url)
    except Exception as e: print(f"ERROR: {e}", file=sys.stderr); return 2
    posts = links_on(final, index_text)
    if not posts: posts = [final]
    print(f"Found {len(posts)} post(s). Inspecting with {args.workers} workers…")
    results = []
    def one(item):
        u, i = item
        try:
            r = inspect_page(u); r["number"] = i; return r
        except Exception as e: return {"number": i, "page_url": u, "error": str(e), "title": "", "direct_urls": [], "embed_urls": []}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(one, [(u, i) for i, u in enumerate(posts, 1)]):
            results.append(r)
            media = r.get("direct_urls") or r.get("embed_urls")
            print(f"[{r['number']:03d}] {r.get('title','')[:65]} | {media[0] if media else 'no public media URL'}")
    if args.download:
        print("\nDownloading direct public URLs only…")
        folder = Path(args.out)
        for r in results:
            for j, u in enumerate(r.get("direct_urls", []), 1):
                r.setdefault("download_status", []).append(download(u, folder, r.get("title"), r["number"]))
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved report: {args.json}")
    else:
        Path("video_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Saved report: video_results.json")
    print("Done. Blogger token embeds may not have a stable direct download URL.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
