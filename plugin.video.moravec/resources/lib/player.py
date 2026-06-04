"""
Helper pro vytváření Kodi ListItem pro přehrávání HLS streamů.
"""

import xbmcgui


def create_hls_item(stream_url: str, metadata: dict) -> xbmcgui.ListItem:
    """
    Vytvoří ListItem nakonfigurovaný pro HLS přehrávání přes inputstream.adaptive.

    metadata slovník: title, plot, thumbnail, duration
    """
    item = xbmcgui.ListItem(label=metadata.get("title", ""))

    # Nastavit metadata pro OSD (info panel při přehrávání)
    info_tag = item.getVideoInfoTag()
    info_tag.setTitle(metadata.get("title", ""))
    info_tag.setPlot(metadata.get("description", ""))
    if metadata.get("duration"):
        info_tag.setDuration(int(metadata["duration"]))

    # Thumbnail
    if metadata.get("thumbnail"):
        item.setArt({"thumb": metadata["thumbnail"], "poster": metadata["thumbnail"]})

    # Nastavit jako přehrávatelný (ne adresář)
    item.setProperty("IsPlayable", "true")

    # Použít inputstream.adaptive pro HLS – podporuje adaptivní bitrate
    item.setProperty("inputstream", "inputstream.adaptive")
    item.setProperty("inputstream.adaptive.manifest_type", "hls")
    item.setMimeType("application/x-mpegURL")
    item.setContentLookup(False)

    item.setPath(stream_url)
    return item
