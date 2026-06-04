"""
Tivio/Firebase API klient pro moravec.cz

Architektura:
  - Auth:    Firebase Auth (email+heslo, tenant: XC88VmVyEGBJcBb9gQG9-tfdxu)
  - Obsah:   Firestore REST API (kolekce videos, organizations/{ORG_ID}/tags)
  - Stream:  Cloud Function getSourceUrl (europe-west3)
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

FIREBASE_API_KEY = "AIzaSyB02udgMkNLADkLJ_w5YNBMR2VR1WHfusI"
FIREBASE_PROJECT_ID = "tivio-production"
FIREBASE_TENANT_ID = "XC88VmVyEGBJcBb9gQG9-tfdxu"

# ID moravec organizace v Firestore
ORG_ID = "fC88VmVyEGBJcBb9gQG9"

FIREBASE_AUTH_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={FIREBASE_API_KEY}"
)
FIREBASE_REFRESH_URL = (
    f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
)
FIRESTORE_BASE_URL = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
    "/databases/(default)/documents"
)
# Cloud Function pro získání HLS stream URL
GET_SOURCE_URL_FUNCTION = (
    "https://europe-west3-tivio-production.cloudfunctions.net/getSourceUrl"
)

# HLS capabilities – H264 bez DRM (Kodi/LibreELEC nepotřebuje Widevine pro HLS)
HLS_CAPABILITIES = [
    {"codec": "h264", "protocol": "hls", "encryption": "none"},
]

# Cache pro auth token
_TOKEN_CACHE_PATH = None


def set_token_cache_path(path: str) -> None:
    global _TOKEN_CACHE_PATH
    _TOKEN_CACHE_PATH = path


class ApiError(Exception):
    pass


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_post(url: str, data: dict, headers: dict = None) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ApiError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}") from e


def _http_get(url: str, token: str = None) -> dict:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ApiError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}") from e


# ── Autentizace ───────────────────────────────────────────────────────────────

def sign_in(email: str, password: str) -> dict:
    """Přihlásí uživatele přes Firebase Auth (s Tivio tenant ID)."""
    resp = _http_post(FIREBASE_AUTH_URL, {
        "email": email,
        "password": password,
        "returnSecureToken": True,
        "tenantId": FIREBASE_TENANT_ID,
    })
    _save_token_cache(resp)
    return resp


def _refresh_id_token(refresh_token: str) -> dict:
    resp = _http_post(FIREBASE_REFRESH_URL, {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    normalized = {
        "idToken": resp.get("id_token"),
        "refreshToken": resp.get("refresh_token"),
        "expiresIn": resp.get("expires_in", "3600"),
    }
    _save_token_cache(normalized)
    return normalized


def _save_token_cache(token_data: dict) -> None:
    if not _TOKEN_CACHE_PATH:
        return
    cache = {
        "id_token": token_data.get("idToken"),
        "refresh_token": token_data.get("refreshToken"),
        "expires_at": time.time() + int(token_data.get("expiresIn", 3600)) - 60,
    }
    os.makedirs(os.path.dirname(_TOKEN_CACHE_PATH), exist_ok=True)
    with open(_TOKEN_CACHE_PATH, "w") as f:
        json.dump(cache, f)


def get_valid_token() -> str:
    """Vrátí platný idToken (z cache nebo po refresh)."""
    if not _TOKEN_CACHE_PATH or not os.path.exists(_TOKEN_CACHE_PATH):
        raise ApiError("not_authenticated")
    with open(_TOKEN_CACHE_PATH) as f:
        cache = json.load(f)
    if time.time() < cache.get("expires_at", 0):
        return cache["id_token"]
    try:
        return _refresh_id_token(cache["refresh_token"])["idToken"]
    except ApiError:
        # Refresh selhal (např. po změně hesla) – smazat cache a vyžádat znovu přihlášení
        os.remove(_TOKEN_CACHE_PATH)
        raise ApiError("not_authenticated")


# ── Firestore helpers ─────────────────────────────────────────────────────────

def _fs_value(field_value: dict):
    """Převede Firestore field value na Python hodnotu."""
    if "stringValue" in field_value:
        return field_value["stringValue"]
    if "integerValue" in field_value:
        return int(field_value["integerValue"])
    if "booleanValue" in field_value:
        return field_value["booleanValue"]
    if "timestampValue" in field_value:
        return field_value["timestampValue"]
    if "referenceValue" in field_value:
        # Vrátit Firestore cestu (např. "organizations/xxx/tags/yyy")
        return field_value["referenceValue"]
    if "arrayValue" in field_value:
        return [_fs_value(v) for v in field_value["arrayValue"].get("values", [])]
    if "mapValue" in field_value:
        return _fs_doc_to_dict(field_value["mapValue"].get("fields", {}))
    if "nullValue" in field_value:
        return None
    return None


def _fs_doc_to_dict(fields: dict) -> dict:
    return {k: _fs_value(v) for k, v in fields.items()}


def _fs_query(collection: str, field: str, op: str, value: dict, token: str,
              limit: int = 50, order_by: str = None) -> list[dict]:
    """Spustí Firestore structured query."""
    query = {
        "structuredQuery": {
            "from": [{"collectionId": collection}],
            "where": {
                "fieldFilter": {
                    "field": {"fieldPath": field},
                    "op": op,
                    "value": value,
                }
            },
            "limit": limit,
        }
    }
    if order_by:
        query["structuredQuery"]["orderBy"] = [{"field": {"fieldPath": order_by}, "direction": "DESCENDING"}]

    url = f"{FIRESTORE_BASE_URL}:runQuery"
    data = _http_post(url, query, headers={"Authorization": f"Bearer {token}"})
    result = []
    for item in data:
        doc = item.get("document")
        if doc:
            doc_id = doc["name"].split("/")[-1]
            fields_dict = _fs_doc_to_dict(doc.get("fields", {}))
            fields_dict["_id"] = doc_id
            result.append(fields_dict)
    return result


def _extract_image_url(doc: dict) -> str:
    """Extrahuje URL obrázku z assets pole."""
    assets = doc.get("assets") or {}
    if isinstance(assets, dict):
        # Preferovat cover @2 nebo @1
        for asset_key in ("cover", "banner", "background_banner_mobile"):
            asset = assets.get(asset_key) or {}
            for scale in ("@2", "@1", "@3"):
                entry = asset.get(scale) or {}
                url = entry.get("background") or entry.get("url")
                if url:
                    return url
    return ""


# ── Obsah moravec.cz ─────────────────────────────────────────────────────────

# Generické placeholder názvy tagů – ty zobrazovat nechceme
_IGNORED_TAG_NAMES = {"tag", "test", "new screen 2"}


def get_shows() -> list[dict]:
    """
    Vrátí seznam pořadů = tagy moravec organizace.
    Filtruje generické tagy (name='Tag', 'test' apod.).
    """
    token = get_valid_token()
    url = f"{FIRESTORE_BASE_URL}/organizations/{ORG_ID}/tags?pageSize=50"
    data = _http_get(url, token=token)
    docs = data.get("documents", [])
    result = []
    for d in docs:
        tag_id = d["name"].split("/")[-1]
        fields = _fs_doc_to_dict(d.get("fields", {}))
        name_map = fields.get("name") or {}
        name = name_map.get("cs") or name_map.get("en") or tag_id
        if name.lower() in _IGNORED_TAG_NAMES:
            continue
        result.append({
            "id": tag_id,
            "title": name,
            "description": (fields.get("description") or "").strip(),
            "thumbnail": _extract_image_url(fields),
        })
    # Seřadit abecedně
    result.sort(key=lambda x: x["title"])
    return result


def get_all_videos(limit: int = 100) -> list[dict]:
    """Vrátí všechna videa moravec organizace (pro záložku 'Vše')."""
    token = get_valid_token()
    org_ref = f"projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/organizations/{ORG_ID}"
    videos = _fs_query(
        collection="videos",
        field="organizationRef",
        op="EQUAL",
        value={"referenceValue": org_ref},
        token=token,
        limit=limit,
        order_by="created",
    )
    return [_normalize_video(v) for v in videos if v.get("publishedStatus") == "PUBLISHED"]


def get_videos_by_tag(tag_id: str, limit: int = 50) -> list[dict]:
    """Vrátí videa označená daným tagem (pořadem)."""
    token = get_valid_token()
    tag_ref = (
        f"projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents"
        f"/organizations/{ORG_ID}/tags/{tag_id}"
    )
    # Firestore ARRAY_CONTAINS pro referenční hodnotu
    videos = _fs_query(
        collection="videos",
        field="tags",
        op="ARRAY_CONTAINS",
        value={"referenceValue": tag_ref},
        token=token,
        limit=limit,
        order_by="created",
    )
    return [_normalize_video(v) for v in videos if v.get("publishedStatus") == "PUBLISHED"]


def _normalize_video(v: dict) -> dict:
    """Normalizuje video dokument do jednotného formátu."""
    name_map = v.get("name") or {}
    desc_map = v.get("descriptionRich") or v.get("description") or {}
    return {
        "id": v.get("_id"),
        "title": name_map.get("cs") or name_map.get("en") or v.get("defaultName") or v.get("_id"),
        "description": (desc_map.get("cs") or desc_map.get("en") or "").strip(),
        "thumbnail": _extract_image_url(v),
        "duration": int(v.get("duration") or 0) // 1000,  # ms → sekundy
        "published": (v.get("created") or "")[:10],
    }


def get_stream_url(video_id: str) -> str:
    """
    Získá HLS stream URL přes Tivio Cloud Function getSourceUrl.
    Vrátí .m3u8 URL připravenou pro inputstream.adaptive.
    """
    token = get_valid_token()
    resp = _http_post(
        GET_SOURCE_URL_FUNCTION,
        {
            "data": {
                "id": video_id,
                "documentType": "video",
                "capabilities": HLS_CAPABILITIES,
            }
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    result = resp.get("result") or {}
    url = result.get("url")
    if not url:
        raise ApiError(f"getSourceUrl nevrátila URL pro video {video_id}")
    return url
