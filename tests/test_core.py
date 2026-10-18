"""Tests für Token, Vault-Abschottung, Frontmatter und Rendering."""

from __future__ import annotations

import os

import pytest

from obsidian_share import render, share_token, vault as v


# -- Token -----------------------------------------------------------------


def test_token_roundtrip_and_expiry():
    key = share_token.new_key()
    tok = share_token.encode(key, "Ordner/Notiz.md", 1000)
    assert "Notiz" not in tok
    assert share_token.decode(key, tok, 999) == ("Ordner/Notiz.md", 1000)
    assert share_token.decode(key, tok, 1001) is None


def test_token_no_expiry_and_wrong_key():
    key = share_token.new_key()
    tok = share_token.encode(key, "a.md", None)
    assert share_token.decode(key, tok, 10**12) == ("a.md", None)
    assert share_token.decode(share_token.new_key(), tok, 0) is None


@pytest.mark.parametrize("bad", ["", "x", "!!!!", "A" * 3000])
def test_token_garbage(bad):
    assert share_token.decode(share_token.new_key(), bad, 0) is None


def test_token_tampered():
    key = share_token.new_key()
    tok = share_token.encode(key, "a.md", None)
    flipped = tok[:-2] + ("A" if tok[-2] != "A" else "B") + tok[-1]
    assert share_token.decode(key, flipped, 0) is None


# -- Vault -----------------------------------------------------------------


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "Ordner").mkdir()
    (tmp_path / "Ordner" / "Notiz.md").write_text("---\nha_share: true\n---\n# Titel\n", "utf-8")
    (tmp_path / "Ordner" / "bild.png").write_bytes(b"\x89PNG")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "geheim.md").write_text("x", "utf-8")
    (tmp_path.parent / "draussen.md").write_text("x", "utf-8")
    os.symlink(tmp_path.parent / "draussen.md", tmp_path / "link.md")
    return v.Vault(str(tmp_path))


@pytest.mark.parametrize(
    "rel",
    ["../draussen.md", "/etc/passwd.md", ".obsidian/geheim.md", "Ordner/../../draussen.md",
     "link.md", "Ordner/bild.png", "", "a\x00.md"],
)
def test_vault_rejects(vault, rel):
    with pytest.raises(v.NotFound):
        vault.read_note(rel)


def test_vault_lists_only_visible(vault):
    paths = [n["path"] for n in vault.list_notes()]
    assert "Ordner/Notiz.md" in paths
    assert not any(p.startswith(".obsidian") for p in paths)
    assert next(n for n in vault.list_notes() if n["path"] == "Ordner/Notiz.md")["shared"]


def test_vault_write_conflict(vault):
    text, etag = vault.read_note("Ordner/Notiz.md")
    new_etag = vault.write_note("Ordner/Notiz.md", text + "neu\n", etag)
    assert new_etag != etag
    with pytest.raises(v.Conflict):
        vault.write_note("Ordner/Notiz.md", "alt", etag)
    leftovers = [p for p in os.listdir(vault.root / "Ordner") if p.endswith(v.TMP_SUFFIX)]
    assert leftovers == []


# -- Frontmatter -----------------------------------------------------------


def test_share_flag_roundtrip():
    text = "---\ntags: [a]\n---\nBody\n"
    on = v.set_share_flag(text, True)
    assert v.is_shared(v.split_frontmatter(on)[0])
    assert "tags: [a]" in on and on.endswith("Body\n")
    off = v.set_share_flag(on, False)
    assert off == text


def test_share_flag_without_frontmatter():
    on = v.set_share_flag("Body\n", True)
    assert on.startswith("---\nha_share: true\n---\n")
    assert v.set_share_flag(on, False) == "Body\n"


# -- Rendering -------------------------------------------------------------


def _render(text, mode=render.MODE_PUBLIC, files=("Ordner/Notiz.md", "Ordner/bild.png", "Andere.md")):
    index = v.FileIndex()
    for rel in files:
        index.all.add(rel)
        index.by_name.setdefault(rel.rsplit("/", 1)[-1].lower(), []).append(rel)
    return render.render_note(
        text, note_rel="Ordner/Notiz.md", index=index, mode=mode, image_url=lambda i, r: f"/img/{i}"
    )


def test_render_no_raw_html():
    out = _render("<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>").html
    assert "<script" not in out and "<img src=x" not in out


def test_render_callout_wikilink_embed_comment():
    out = _render(
        "> [!warning]- Achtung\n> Inhalt\n\n[[Andere|Link]] ![[bild.png|200]] %%geheim%%\n\n# A\n## B\n## B"
    )
    assert 'data-callout="warning"' in out.html and "<details" in out.html
    assert "geheim" not in out.html
    assert 'src="/img/0"' in out.html and 'width="200"' in out.html
    assert out.embeds == ["Ordner/bild.png"]
    assert [t["id"] for t in out.toc] == ["a", "b", "b-1"]
    panel = _render("[[Andere]]", mode=render.MODE_PANEL).html
    assert 'data-note="Andere.md"' in panel


def test_render_external_image_not_loaded():
    out = _render("![x](https://example.com/a.png)").html
    assert "<img" not in out and 'rel="noopener noreferrer nofollow"' in out


def test_render_frontmatter_hidden():
    out = _render("---\nha_share: true\n---\nText").html
    assert "ha_share" not in out
