"""
plugin.video.moravec – Kodi video plugin pro moravec.cz

Vstupní bod a URL router.
URL schéma: plugin://plugin.video.moravec/?action=<akce>&<params>

Akce:
  (prázdné)              → zobrazit seznam pořadů
  list_episodes          → zobrazit epizody pořadu (param: series_id)
  play                   → přehrát video (param: video_id, title, thumbnail, description)
"""

import sys
import urllib.parse

import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

# Přidat resources/lib do sys.path
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "resources", "lib"))

import api
import player

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
PLUGIN_URL = sys.argv[0]
HANDLE = int(sys.argv[1])

# Přeložit Kodi special:// cestu na skutečnou filesystem cestu
TOKEN_CACHE = os.path.join(
    xbmcvfs.translatePath(ADDON.getAddonInfo("profile")), "token_cache.json"
)
api.set_token_cache_path(TOKEN_CACHE)


def _build_url(action: str, **params) -> str:
    """Sestaví plugin URL pro navigaci v menu."""
    query = urllib.parse.urlencode({"action": action, **params})
    return f"{PLUGIN_URL}?{query}"


def _get_params() -> dict:
    """Parsuje parametry z aktuální plugin URL."""
    query = sys.argv[2].lstrip("?") if len(sys.argv) > 2 else ""
    return dict(urllib.parse.parse_qsl(query))


def _ensure_authenticated() -> bool:
    """
    Zkontroluje přihlášení; pokud token chybí, přihlásí se pomocí
    uložených credentials. Vrátí False pokud přihlášení selže.
    """
    try:
        api.get_valid_token()
        return True
    except api.ApiError as e:
        if "not_authenticated" in str(e):
            email = ADDON.getSetting("email").strip()
            password = ADDON.getSetting("password").strip()
            if not email or not password:
                xbmcgui.Dialog().ok(
                    "Moravec.cz – nepřihlášen",
                    "Zadejte e-mail a heslo v nastavení doplňku.",
                )
                ADDON.openSettings()
                return False
            try:
                api.sign_in(email, password)
                return True
            except api.ApiError as auth_err:
                xbmcgui.Dialog().ok(
                    "Moravec.cz – chyba přihlášení",
                    "Zkontrolujte e-mail a heslo.[CR]"
                    f"Chyba: {str(auth_err)[:120]}",
                )
                ADDON.openSettings()
                return False
        raise


def list_shows() -> None:
    """Zobrazí seznam pořadů (tagy) jako hlavní menu."""
    if not _ensure_authenticated():
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    try:
        shows = api.get_shows()
    except api.ApiError as e:
        xbmcgui.Dialog().notification(ADDON_ID, str(e))
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    # Přidat položku "Vše" na začátek
    all_item = xbmcgui.ListItem(label="Vše")
    xbmcplugin.addDirectoryItem(
        HANDLE, _build_url("list_videos", tag_id="__all__"), all_item, isFolder=True
    )

    for s in shows:
        item = xbmcgui.ListItem(label=s["title"])
        if s["thumbnail"]:
            item.setArt({"thumb": s["thumbnail"], "poster": s["thumbnail"]})
        info_tag = item.getVideoInfoTag()
        info_tag.setTitle(s["title"])
        info_tag.setPlot(s["description"])
        info_tag.setMediaType("tvshow")
        url = _build_url("list_videos", tag_id=s["id"])
        xbmcplugin.addDirectoryItem(HANDLE, url, item, isFolder=True)

    xbmcplugin.setContent(HANDLE, "tvshows")
    xbmcplugin.endOfDirectory(HANDLE)


def list_videos(tag_id: str) -> None:
    """Zobrazí videa pro daný pořad (tag) nebo všechna videa."""
    if not _ensure_authenticated():
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    try:
        if tag_id == "__all__":
            videos = api.get_all_videos()
        else:
            videos = api.get_videos_by_tag(tag_id)
    except api.ApiError as e:
        xbmcgui.Dialog().notification(ADDON_ID, str(e))
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    for ep in videos:
        item = xbmcgui.ListItem(label=ep["title"])
        if ep["thumbnail"]:
            item.setArt({"thumb": ep["thumbnail"], "poster": ep["thumbnail"]})
        item.setProperty("IsPlayable", "true")

        info_tag = item.getVideoInfoTag()
        info_tag.setTitle(ep["title"])
        info_tag.setPlot(ep["description"])
        info_tag.setMediaType("episode")
        if ep.get("duration"):
            info_tag.setDuration(int(ep["duration"]))
        if ep.get("published"):
            info_tag.setPremiered(ep["published"][:10])

        url = _build_url(
            "play",
            video_id=ep["id"],
            title=urllib.parse.quote(ep["title"]),
            thumbnail=urllib.parse.quote(ep["thumbnail"]),
            description=urllib.parse.quote(ep["description"]),
        )
        xbmcplugin.addDirectoryItem(HANDLE, url, item, isFolder=False)

    xbmcplugin.setContent(HANDLE, "episodes")
    xbmcplugin.endOfDirectory(HANDLE)


def play_video(params: dict) -> None:
    """Přeloží video_id na HLS URL a spustí přehrávání."""
    video_id = params["video_id"]

    try:
        stream_url = api.get_stream_url(video_id)
    except api.ApiError as e:
        xbmcgui.Dialog().ok(
            ADDON.getLocalizedString(32021),
            ADDON.getLocalizedString(32022),
        )
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    metadata = {
        "title": urllib.parse.unquote(params.get("title", "")),
        "description": urllib.parse.unquote(params.get("description", "")),
        "thumbnail": urllib.parse.unquote(params.get("thumbnail", "")),
    }
    list_item = player.create_hls_item(stream_url, metadata)
    xbmcplugin.setResolvedUrl(HANDLE, True, list_item)


def router() -> None:
    """Hlavní router – volá správnou funkci podle URL parametrů."""
    params = _get_params()
    action = params.get("action")

    if not action:
        list_shows()
    elif action == "list_videos":
        list_videos(params["tag_id"])
    elif action == "play":
        play_video(params)
    else:
        xbmcgui.Dialog().notification(ADDON_ID, f"Neznámá akce: {action}")


if __name__ == "__main__":
    router()
