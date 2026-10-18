"""HTTP-Endpunkte: öffentlicher Lese-Link und Panel-API."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components.http import KEY_HASS_USER, HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import API_BASE, DOMAIN, MAX_SHARE_DAYS
from .render import NOT_FOUND_PAGE
from .runtime import ShareRuntime
from .vault import Conflict, NotFound, TooLarge, VaultError, is_shared, set_share_flag, split_frontmatter

PUBLIC_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}
# SVG kann Skripte enthalten: beim direkten Aufruf durch CSP-Sandbox entschärfen
IMAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _runtime(hass: HomeAssistant) -> ShareRuntime | None:
    return hass.data.get(DOMAIN)


def _not_found() -> web.Response:
    return web.Response(
        text=NOT_FOUND_PAGE,
        content_type="text/html",
        status=HTTPStatus.NOT_FOUND,
        headers=PUBLIC_HEADERS,
    )


class _Base(HomeAssistantView):
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass


class PublicNoteView(_Base):
    """Öffentlich: eine freigegebene Notiz, nur lesen."""

    url = f"{API_BASE}/s/{{token}}"
    name = "api:obsidian_share:public"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        runtime = _runtime(self.hass)
        page = await runtime.async_public_page(token) if runtime else None
        if page is None:
            return _not_found()
        return web.Response(text=page, content_type="text/html", headers=PUBLIC_HEADERS)


class PublicImageView(_Base):
    """Öffentlich: ein Bild, das die freigegebene Notiz selbst einbettet."""

    url = f"{API_BASE}/s/{{token}}/img/{{idx:\\d{{1,4}}}}"
    name = "api:obsidian_share:public_image"
    requires_auth = False

    async def get(self, request: web.Request, token: str, idx: str) -> web.Response:
        runtime = _runtime(self.hass)
        image = await runtime.async_public_image(token, int(idx)) if runtime else None
        if image is None:
            return _not_found()
        data, ctype = image
        return web.Response(body=data, content_type=ctype, headers=IMAGE_HEADERS)


class _PanelView(_Base):
    requires_auth = True

    def _ctx(self, request: web.Request, *, edit: bool = False):
        runtime = _runtime(self.hass)
        if runtime is None:
            raise web.HTTPServiceUnavailable
        user = request[KEY_HASS_USER]
        allowed = runtime.can_edit(user) if edit else runtime.can_read(user)
        if not allowed:
            raise web.HTTPForbidden
        return runtime, user

    @staticmethod
    def _error(err: VaultError) -> web.Response:
        if isinstance(err, Conflict):
            return HomeAssistantView.json(
                {"error": "conflict", "etag": err.etag}, HTTPStatus.CONFLICT
            )
        if isinstance(err, TooLarge):
            return HomeAssistantView.json({"error": "too_large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        return HomeAssistantView.json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    @staticmethod
    async def _body(request: web.Request, schema: vol.Schema) -> dict[str, Any]:
        try:
            return schema(await request.json())
        except (ValueError, vol.Invalid) as err:
            raise web.HTTPBadRequest(text=str(err)) from err


class TreeView(_PanelView):
    """Alle Notizen mit Freigabestatus."""

    url = f"{API_BASE}/tree"
    name = "api:obsidian_share:tree"

    async def get(self, request: web.Request) -> web.Response:
        runtime, user = self._ctx(request)
        notes = await self.hass.async_add_executor_job(runtime.vault.list_notes)
        return self.json({"notes": notes, "can_edit": runtime.can_edit(user)})


SAVE_SCHEMA = vol.Schema({vol.Required("path"): str, vol.Required("text"): str, vol.Required("etag"): str})
SHARE_SCHEMA = vol.Schema(
    {
        vol.Required("path"): str,
        vol.Required("enabled"): bool,
        vol.Optional("etag"): vol.Any(None, str),
        vol.Optional("days"): vol.Any(None, vol.All(int, vol.Range(min=1, max=MAX_SHARE_DAYS))),
    }
)


class NoteView(_PanelView):
    """Notiz lesen (gerendert + roh) und speichern."""

    url = f"{API_BASE}/note"
    name = "api:obsidian_share:note"

    async def get(self, request: web.Request) -> web.Response:
        runtime, user = self._ctx(request)
        try:
            data = await runtime.async_panel_note(request.query.get("path", ""))
        except VaultError as err:
            return self._error(err)
        data["can_edit"] = runtime.can_edit(user)
        return self.json(data)

    async def put(self, request: web.Request) -> web.Response:
        runtime, _ = self._ctx(request, edit=True)
        body = await self._body(request, SAVE_SCHEMA)
        try:
            etag = await self.hass.async_add_executor_job(
                runtime.vault.write_note, body["path"], body["text"], body["etag"]
            )
        except VaultError as err:
            return self._error(err)
        return self.json({"etag": etag})


class ShareView(_PanelView):
    """Freigabe setzen/beenden und Link erzeugen."""

    url = f"{API_BASE}/share"
    name = "api:obsidian_share:share"

    async def post(self, request: web.Request) -> web.Response:
        runtime, _ = self._ctx(request, edit=True)
        body = await self._body(request, SHARE_SCHEMA)
        path, enabled = body["path"], body["enabled"]

        def apply() -> str:
            text, etag = runtime.vault.read_note(path)
            if body.get("etag") and body["etag"] != etag:
                raise Conflict(etag)
            meta, _ = split_frontmatter(text)
            if is_shared(meta) == enabled:
                return etag
            return runtime.vault.write_note(path, set_share_flag(text, enabled), etag)

        try:
            etag = await self.hass.async_add_executor_job(apply)
        except VaultError as err:
            return self._error(err)
        result: dict[str, Any] = {"etag": etag, "shared": enabled}
        if enabled:
            result["url"], result["expires"] = runtime.make_link(path, body.get("days"))
        return self.json(result)


class FileView(_PanelView):
    """Bild für das Panel (per signierter URL)."""

    url = f"{API_BASE}/file"
    name = "api:obsidian_share:file"

    async def get(self, request: web.Request) -> web.Response:
        runtime, _ = self._ctx(request)
        try:
            data, ctype = await self.hass.async_add_executor_job(
                runtime.vault.read_image, request.query.get("path", "")
            )
        except (NotFound, VaultError):
            raise web.HTTPNotFound from None
        headers = {**IMAGE_HEADERS, "Cache-Control": "private, max-age=600"}
        return web.Response(body=data, content_type=ctype, headers=headers)


ALL_VIEWS = (PublicNoteView, PublicImageView, TreeView, NoteView, ShareView, FileView)
