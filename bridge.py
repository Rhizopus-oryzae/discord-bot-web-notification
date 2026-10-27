#!/usr/bin/env python3
"""Local RSS bridge for www.yasir252.com.

Site has no native RSS and its WordPress REST API is auth-only (403
rest_forbidden), so this tiny bridge fetches the homepage with a browser
User-Agent (Cloudflare passes that; it only challenges headless browsers /
heavy hammering) and emits a valid RSS 2.0 feed (<guid>=URL -> dedup key,
<description>=excerpt, <pubDate> from the post <time>) that the bot's
existing feedparser pipeline consumes unchanged.

Theme maxblog2 renders each post as <h3>..</h3><div..><time datetime=..>..</time></div>
<p>{title} {excerpt}</p> — we strip the title prefix from <p> to recover the
true excerpt, so Discord messages are no longer blank.
"""
import os
import re
import html
import urllib.request
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "https://www.yasir252.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.6610.130 Safari/537.36")


def fetch_home():
    req = urllib.request.Request(BASE, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def _text(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or ""))).strip()


def _norm_token(w):
    return w.strip(".,;:!?()[]\"'\u201c\u201d").lower()


def _strip_title_prefix(desc, title):
    """Theme renders each card as '<p>{title} [badge-word?] {excerpt}</p>';
    consume the leading title tokens in order (allowing one interspersed badge
    word such as 'Mitos?') so only the real excerpt remains."""
    desc = desc.strip()
    if not desc or not title:
        return desc
    ttoks = [t for t in (_norm_token(w) for w in title.split()) if t]
    dtok = desc.split()
    ti = 0
    out = []
    for w in dtok:
        nw = _norm_token(w)
        if ti < len(ttoks) and nw == ttoks[ti]:
            ti += 1
            continue
        if ti < len(ttoks):
            # badge word inside the title run -> drop
            continue
        out.append(w)
    return (" ".join(out)).strip() or desc


def extract_posts(src):
    """Return newest-first list of {title,url,desc,pub} from the homepage."""
    posts = []
    seen = set()
    for m in re.finditer(r"<h3[^>]*>(.*?)</h3>", src, re.S):
        inner = m.group(1)
        a = re.search(r'href="(https://www\.yasir252\.com/[^"]+)"[^>]*>(.*?)</a>', inner, re.S)
        if not a:
            continue
        url = a.group(1)
        title = _text(a.group(2))
        # excerpt lives in the first <p> after the closing </h3>
        after = m.end()
        window = src[after:after + 1400]
        p = re.search(r"<p>(.*?)</p>", window, re.S)
        desc = _text(p.group(1)) if p else ""
        # site renders "<p>{title} [badge?] {excerpt}</p>"; keep only excerpt
        desc = _strip_title_prefix(desc, title)
        # publication date from nearby <time datetime="..">
        t = re.search(r'<time[^>]*datetime="([^"]+)"', window)
        pub = ""
        if t:
            try:
                dt = datetime.datetime.fromisoformat(t.group(1))
                pub = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except ValueError:
                pub = ""
        if url in seen:
            continue
        seen.add(url)
        posts.append({"title": title, "url": url, "desc": desc[:320], "pub": pub})
    # homepage lists newest first; keep DOM order (dedup already done)
    return posts


def rss_xml(posts, limit=5):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        "<title>www.yasir252.com</title>",
        "<link>https://www.yasir252.com/</link>",
        "<description>Yasir252 latest articles (local RSS bridge; site has no native RSS)</description>",
        "<lastBuildDate>{}</lastBuildDate>".format(now),
    ]
    count = 0
    for p in posts:
        if count >= limit:
            break
        out.append("  <item>")
        out.append("    <title>{}</title>".format(html.escape(p["title"])))
        out.append("    <link>{}</link>".format(html.escape(p["url"])))
        out.append('    <guid isPermaLink="false">{}</guid>'.format(html.escape(p["url"])))
        if p["pub"]:
            out.append("    <pubDate>{}</pubDate>".format(p["pub"]))
        out.append("    <description>{}</description>".format(html.escape(p["desc"])))
        out.append("  </item>")
        count += 1
    out.append("</channel>")
    out.append("</rss>")
    return "\n".join(out)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/healthz", "/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path.startswith("/yasir252.xml") or self.path.startswith("/feed"):
            try:
                posts = extract_posts(fetch_home())
                limit = int(os.environ.get("BRIDGE_LIMIT", "5"))
                xml = rss_xml(posts, limit)
                data = xml.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except Exception as e:
                msg = "bridge error: %s" % e
                self.send_response(502)
                self.end_headers()
                self.wfile.write(msg.encode())
                return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "12000"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
