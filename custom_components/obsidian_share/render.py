"""Obsidian-Markdown → sicheres HTML.

Roh-HTML wird nie durchgereicht (markdown-it mit html=False). Unterstützt:
Callouts (auch einklappbar), Wikilinks, Bild-Einbettungen ![[…]], Aufgaben,
Tabellen, Durchgestrichenes, %%Kommentare%% und Überschriften-Anker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import html
import posixpath
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from markdown_it.rules_inline import StateInline
from mdit_py_plugins.tasklists import tasklists_plugin

from .vault import IMAGE_TYPES, NOTE_SUFFIX, FileIndex, split_frontmatter

MODE_PUBLIC = "public"
MODE_PANEL = "panel"

_CALLOUT_RE = re.compile(r"^\[!([A-Za-z][\w-]*)\]([+-]?)[ \t]*(.*)$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_COMMENT_RE = re.compile(r"%%.*?%%", re.DOTALL)
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_SIZE_RE = re.compile(r"^(\d{1,4})(?:x(\d{1,4}))?$")
_WIKI_PLAIN_RE = re.compile(r"!?\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")

esc = html.escape


@dataclass
class RenderContext:
    """Kontext pro Rendervorgang."""

    note_rel: str
    index: FileIndex
    mode: str
    image_url: Callable[[int, str], str]
    embeds: list[str] = field(default_factory=list)
    toc: list[dict] = field(default_factory=list)

    @property
    def note_dir(self) -> str:
        return posixpath.dirname(self.note_rel)


@dataclass
class Rendered:
    """Ergebnis."""

    html: str
    toc: list[dict]
    embeds: list[str]


def slugify(text: str) -> str:
    """Anker-ID aus Überschriftentext."""
    value = unicodedata.normalize("NFKC", text).strip().lower()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value).strip("-")
    return value or "abschnitt"


def strip_comments(text: str) -> str:
    """%%Kommentare%% außerhalb von Codeblöcken entfernen."""
    out: list[str] = []
    buf: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        match = _FENCE_RE.match(line)
        if fence is None:
            if match:
                out.append(_COMMENT_RE.sub("", "".join(buf)))
                buf = []
                fence = match.group(1)
                out.append(line)
            else:
                buf.append(line)
        else:
            out.append(line)
            if (
                match
                and match.group(1)[0] == fence[0]
                and len(match.group(1)) >= len(fence)
                and line.strip() == match.group(1)
            ):
                fence = None
    out.append(_COMMENT_RE.sub("", "".join(buf)))
    return "".join(out)


def resolve_target(ctx: RenderContext, target: str, *, note: bool) -> str | None:
    """Wikilink-/Pfadziel wie Obsidian auflösen (kürzester passender Pfad)."""
    target = target.strip().replace("\\", "/").lstrip("/")
    if not target:
        return None
    if note and posixpath.splitext(target)[1].lower() != NOTE_SUFFIX:
        target += NOTE_SUFFIX
    if "/" in target:
        for base in (ctx.note_dir, ""):
            cand = posixpath.normpath(posixpath.join(base, target))
            if not cand.startswith("../") and cand in ctx.index.all:
                return cand
        tail = "/" + target.lower()
        matches = [p for p in ctx.index.all if ("/" + p.lower()).endswith(tail)]
    else:
        matches = ctx.index.by_name.get(target.lower(), [])
    if not matches:
        return None
    note_dir = ctx.note_dir

    def rank(path: str) -> tuple:
        parent = posixpath.dirname(path)
        near = 0 if parent == note_dir else 1 if path.startswith(note_dir + "/") else 2
        return (near, path.count("/"), len(path), path)

    return min(matches, key=rank)


def _img_html(ctx: RenderContext, rel: str, alt: str, size: str = "") -> str:
    if rel not in ctx.embeds:
        ctx.embeds.append(rel)
    idx = ctx.embeds.index(rel)
    attrs = ""
    if match := _SIZE_RE.match(size.strip()):
        attrs += f' width="{match.group(1)}"'
        if match.group(2):
            attrs += f' height="{match.group(2)}"'
    src = esc(ctx.image_url(idx, rel))
    return f'<img src="{src}" alt="{esc(alt)}" loading="lazy"{attrs}>'


def _note_ref(ctx: RenderContext, rel: str | None, anchor: str, label: str, cls: str) -> str:
    if ctx.mode == MODE_PANEL and rel:
        return (
            f'<a href="#" class="{cls}" data-note="{esc(rel)}" '
            f'data-anchor="{esc(anchor)}">{esc(label)}</a>'
        )
    if not rel:
        cls += " unresolved"
    return f'<span class="{cls}">{esc(label)}</span>'


# -- markdown-it Regeln ----------------------------------------------------


def _wikilink_rule(state: StateInline, silent: bool) -> bool:
    src, pos = state.src, state.pos
    embed = src.startswith("![[", pos)
    if not embed and not src.startswith("[[", pos):
        return False
    start = pos + (3 if embed else 2)
    end = src.find("]]", start)
    if end == -1:
        return False
    inner = src[start:end]
    if not inner.strip() or "\n" in inner or "[" in inner:
        return False
    if not silent:
        token = state.push("obsidian_link", "", 0)
        token.meta = {"inner": inner, "embed": embed}
    state.pos = end + 2
    return True


def _callout_rule(state: StateCore) -> None:
    tokens = state.tokens
    for i, tok in enumerate(tokens):
        if tok.type != "blockquote_open" or i + 3 >= len(tokens):
            continue
        para, inline = tokens[i + 1], tokens[i + 2]
        if para.type != "paragraph_open" or inline.type != "inline":
            continue
        first, _, rest = inline.content.partition("\n")
        match = _CALLOUT_RE.match(first.strip())
        if not match:
            continue
        info = {"type": match.group(1).lower(), "fold": match.group(2), "title": match.group(3)}
        tok.meta = {**(tok.meta or {}), "callout": info}
        inline.content = rest
        if not rest.strip():
            para.hidden = True
            tokens[i + 3].hidden = True
        for close in tokens[i + 1 :]:
            if close.type == "blockquote_close" and close.level == tok.level:
                close.meta = {**(close.meta or {}), "callout": info}
                break


def _plain_heading(content: str) -> str:
    text = _WIKI_PLAIN_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), content)
    return re.sub(r"[*_`~=]", "", text).strip()


def _classify_link(href: str, ctx: RenderContext) -> dict:
    if href.startswith("#"):
        return {"kind": "anchor", "href": "#" + slugify(unquote(href[1:]))}
    if _SCHEME_RE.match(href):
        if href.lower().startswith(("http://", "https://", "mailto:")):
            return {"kind": "external"}
        return {"kind": "text"}
    parts = urlsplit(href)
    path = unquote(parts.path)
    if not path:
        return {"kind": "text"}
    ext = posixpath.splitext(path)[1].lower()
    if ext in ("", NOTE_SUFFIX):
        rel = resolve_target(ctx, path, note=True)
        anchor = slugify(unquote(parts.fragment)) if parts.fragment else ""
        return {"kind": "note", "rel": rel, "anchor": anchor}
    return {"kind": "text"}


def _post_rule(state: StateCore) -> None:
    ctx: RenderContext = state.env["ctx"]
    seen: dict[str, int] = {}
    tokens = state.tokens
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and i + 1 < len(tokens):
            text = _plain_heading(tokens[i + 1].content)
            base = slugify(text)
            count = seen.get(base, 0)
            seen[base] = count + 1
            sid = base if count == 0 else f"{base}-{count}"
            tok.attrSet("id", sid)
            ctx.toc.append({"level": int(tok.tag[1]), "text": text, "id": sid})
        elif tok.type == "inline" and tok.children:
            stack: list[dict] = []
            for child in tok.children:
                if child.type == "link_open":
                    info = _classify_link(str(child.attrGet("href") or ""), ctx)
                    child.meta = {**(child.meta or {}), "os": info}
                    stack.append(info)
                elif child.type == "link_close":
                    child.meta = {**(child.meta or {}), "os": stack.pop() if stack else {}}


# -- Renderer --------------------------------------------------------------


def _r_obsidian_link(self, tokens, idx, options, env) -> str:
    ctx: RenderContext = env["ctx"]
    meta = tokens[idx].meta
    target, _, alias = meta["inner"].partition("|")
    target, alias = target.strip(), alias.strip()
    page, _, heading = target.partition("#")
    page = page.strip()
    if heading.startswith("^"):
        heading = ""
    if meta["embed"]:
        ext = posixpath.splitext(page)[1].lower()
        if ext in IMAGE_TYPES:
            rel = resolve_target(ctx, page, note=False)
            if rel:
                return _img_html(ctx, rel, posixpath.basename(page), alias)
            return f'<span class="missing">{esc(page)}</span>'
        rel = resolve_target(ctx, page, note=True) if ext in ("", NOTE_SUFFIX) else None
        return _note_ref(ctx, rel, slugify(heading) if heading else "", alias or page, "embed")
    if not page:
        label = alias or heading
        return f'<a href="#{slugify(heading)}" class="internal-link">{esc(label)}</a>'
    label = alias or (f"{page} › {heading}" if heading else page)
    rel = resolve_target(ctx, page, note=True)
    return _note_ref(ctx, rel, slugify(heading) if heading else "", label, "internal-link")


def _r_blockquote_open(self, tokens, idx, options, env) -> str:
    info = (tokens[idx].meta or {}).get("callout")
    if not info:
        return self.renderToken(tokens, idx, options, env)
    ctype = esc(info["type"])
    title = info["title"] or info["type"].capitalize()
    title_html = _MD.renderInline(title, env)
    if info["fold"]:
        opened = " open" if info["fold"] == "+" else ""
        return (
            f'<details class="callout" data-callout="{ctype}"{opened}>'
            f'<summary class="callout-title">{title_html}</summary>'
            '<div class="callout-content">\n'
        )
    return (
        f'<div class="callout" data-callout="{ctype}">'
        f'<div class="callout-title">{title_html}</div><div class="callout-content">\n'
    )


def _r_blockquote_close(self, tokens, idx, options, env) -> str:
    info = (tokens[idx].meta or {}).get("callout")
    if not info:
        return self.renderToken(tokens, idx, options, env)
    return "</div></details>\n" if info["fold"] else "</div></div>\n"


def _r_link_open(self, tokens, idx, options, env) -> str:
    ctx: RenderContext = env["ctx"]
    tok = tokens[idx]
    info = (tok.meta or {}).get("os", {})
    kind = info.get("kind")
    if kind == "external":
        tok.attrSet("target", "_blank")
        tok.attrSet("rel", "noopener noreferrer nofollow")
        return self.renderToken(tokens, idx, options, env)
    if kind == "anchor":
        tok.attrSet("href", info["href"])
        return self.renderToken(tokens, idx, options, env)
    if kind == "note" and ctx.mode == MODE_PANEL and info.get("rel"):
        return (
            f'<a href="#" class="internal-link" data-note="{esc(info["rel"])}" '
            f'data-anchor="{esc(info.get("anchor", ""))}">'
        )
    return '<span class="internal-link">' if kind == "note" else "<span>"


def _r_link_close(self, tokens, idx, options, env) -> str:
    ctx: RenderContext = env["ctx"]
    info = (tokens[idx].meta or {}).get("os", {})
    kind = info.get("kind")
    if kind in ("external", "anchor"):
        return "</a>"
    if kind == "note" and ctx.mode == MODE_PANEL and info.get("rel"):
        return "</a>"
    return "</span>"


def _r_image(self, tokens, idx, options, env) -> str:
    ctx: RenderContext = env["ctx"]
    tok = tokens[idx]
    src = str(tok.attrGet("src") or "")
    alt = self.renderInlineAsText(tok.children or [], options, env)
    alt, _, size = alt.partition("|")
    if src.lower().startswith("data:image/"):
        return f'<img src="{esc(src)}" alt="{esc(alt)}">'
    if _SCHEME_RE.match(src):
        if src.lower().startswith(("http://", "https://")):
            # Externe Bilder nicht nachladen (Datenschutz, CSP): als Link zeigen
            return (
                f'<a href="{esc(src)}" target="_blank" rel="noopener noreferrer nofollow">'
                f"{esc(alt or src)}</a>"
            )
        return esc(alt)
    path = unquote(urlsplit(src).path)
    if posixpath.splitext(path)[1].lower() in IMAGE_TYPES:
        rel = resolve_target(ctx, path, note=False)
        if rel:
            return _img_html(ctx, rel, alt, size)
    return f'<span class="missing">{esc(alt or path)}</span>'


def _build() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "breaks": True, "linkify": False})
    md.enable(["table", "strikethrough"])
    md.use(tasklists_plugin)
    md.inline.ruler.before("link", "obsidian_link", _wikilink_rule)
    md.core.ruler.after("block", "obsidian_callouts", _callout_rule)
    md.core.ruler.push("obsidian_post", _post_rule)
    md.add_render_rule("obsidian_link", _r_obsidian_link)
    md.add_render_rule("blockquote_open", _r_blockquote_open)
    md.add_render_rule("blockquote_close", _r_blockquote_close)
    md.add_render_rule("link_open", _r_link_open)
    md.add_render_rule("link_close", _r_link_close)
    md.add_render_rule("image", _r_image)
    return md


_MD = _build()


def render_note(
    text: str,
    *,
    note_rel: str,
    index: FileIndex,
    mode: str,
    image_url: Callable[[int, str], str],
) -> Rendered:
    """Notiztext (inkl. Frontmatter) rendern."""
    _, body = split_frontmatter(text)
    ctx = RenderContext(note_rel=note_rel, index=index, mode=mode, image_url=image_url)
    out = _MD.render(strip_comments(body), {"ctx": ctx})
    return Rendered(html=out, toc=ctx.toc, embeds=ctx.embeds)


# -- Öffentliche Seite -----------------------------------------------------

PUBLIC_CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;
--code:#f6f8fa;--accent:#7c3aed}
@media (prefers-color-scheme:dark){:root{--bg:#1e1e1e;--fg:#dcddde;--muted:#9da3ab;
--line:#3a3a3a;--code:#2a2a2a;--accent:#a78bfa}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:780px;margin:0 auto;padding:24px 18px 64px}
h1.title{font-size:1.9em;line-height:1.25;margin:.2em 0 .6em}
h1,h2,h3,h4{line-height:1.3;scroll-margin-top:12px}
a{color:var(--accent)}
img{max-width:100%;height:auto}
pre{background:var(--code);padding:12px;border-radius:6px;overflow-x:auto}
code{background:var(--code);padding:.1em .3em;border-radius:4px;font-size:.9em}
pre code{padding:0;background:none}
table{border-collapse:collapse;display:block;overflow-x:auto;max-width:100%}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left}
blockquote{margin:1em 0;padding:0 1em;border-left:3px solid var(--line);color:var(--muted)}
hr{border:0;border-top:1px solid var(--line)}
ul.contains-task-list{list-style:none;padding-left:1.2em}
.internal-link{color:var(--accent)}
.unresolved,.missing{opacity:.6}
.toc{border:1px solid var(--line);border-radius:6px;padding:8px 14px;margin:0 0 1.5em}
.toc summary{cursor:pointer;font-weight:600}
.toc ul{list-style:none;padding:0;margin:.5em 0 0}
.toc li.l3{padding-left:1em}.toc li.l4{padding-left:2em}
.callout{--c:68,138,255;border-left:4px solid rgb(var(--c));background:rgba(var(--c),.08);
border-radius:6px;padding:8px 14px;margin:1em 0}
.callout-title{font-weight:600;color:rgb(var(--c))}
details.callout>summary{cursor:pointer}
.callout-content>:last-child{margin-bottom:.3em}
.callout[data-callout=tip],.callout[data-callout=success],.callout[data-callout=check],
.callout[data-callout=done],.callout[data-callout=hint]{--c:8,185,78}
.callout[data-callout=warning],.callout[data-callout=question],.callout[data-callout=help],
.callout[data-callout=caution],.callout[data-callout=attention],.callout[data-callout=faq]{--c:236,117,0}
.callout[data-callout=danger],.callout[data-callout=error],.callout[data-callout=bug],
.callout[data-callout=failure],.callout[data-callout=fail]{--c:233,49,71}
.callout[data-callout=example]{--c:120,82,238}
.callout[data-callout=quote],.callout[data-callout=cite]{--c:158,158,158}
footer{margin-top:3em;color:var(--muted);font-size:.85em;border-top:1px solid var(--line);
padding-top:1em}
"""


def toc_html(toc: list[dict]) -> str:
    """Inhaltsverzeichnis ab drei Überschriften."""
    if len(toc) < 3:
        return ""
    top = min(item["level"] for item in toc)
    items = "".join(
        f'<li class="l{min(item["level"] - top + 2, 4)}">'
        f'<a href="#{esc(item["id"])}">{esc(item["text"])}</a></li>'
        for item in toc
    )
    return f'<details class="toc" open><summary>Inhalt</summary><ul>{items}</ul></details>'


def public_page(title: str, rendered: Rendered, expires_text: str | None) -> str:
    """Komplette HTML-Seite für den öffentlichen Link."""
    footer = "Geteilt aus Obsidian"
    if expires_text:
        footer += f" · Link gültig bis {esc(expires_text)}"
    return (
        "<!doctype html><html lang=de><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        '<meta name=robots content="noindex,nofollow">'
        f"<title>{esc(title)}</title><style>{PUBLIC_CSS}</style></head><body><main>"
        f'<h1 class="title">{esc(title)}</h1>{toc_html(rendered.toc)}'
        f"<article>{rendered.html}</article><footer>{footer}</footer></main></body></html>"
    )


NOT_FOUND_PAGE = (
    "<!doctype html><html lang=de><head><meta charset=utf-8>"
    '<meta name=viewport content="width=device-width,initial-scale=1">'
    '<meta name=robots content="noindex,nofollow"><title>Nicht gefunden</title>'
    f"<style>{PUBLIC_CSS}</style></head><body><main><h1 class=title>Nicht gefunden</h1>"
    "<p>Dieser Link ist ungültig, abgelaufen oder die Freigabe wurde beendet.</p>"
    "</main></body></html>"
)
