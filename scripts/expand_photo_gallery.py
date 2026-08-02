#!/usr/bin/env python3
"""Expand the NativeLingo evaluation gallery with licensed Commons photos.

The selection is intentionally deterministic: every target scene has a fixed
Commons search query and result offset. The manifest retains the source page,
download URL, author and license returned by the MediaWiki API.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from pathlib import Path

from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
_GALLERY = _REPO / "data/photo_gallery"
_CACHE_PATH = _REPO / ".firecrawl/commons-gallery-search-cache.json"
_API = "https://commons.wikimedia.org/w/api.php"
_USER_AGENT = "NativeLingo local model evaluation/0.5"
_ALLOWED_LICENSE_PREFIXES = (
    "CC BY",
    "CC0",
    "Public domain",
    "No restrictions",
)
_UNSUITABLE_TITLE = re.compile(
    r"\b(?:18\d{2}|19\d{2}|drawing|illustration|painting|map|diagram|"
    r"logo|poster|portrait)\b",
    re.IGNORECASE,
)

_TARGETS = [
    # Indoor 11–30
    ("indoor/11-kitchen.jpg", "home kitchen with appliances", "kitchen appliances cabinets", 2),
    ("indoor/12-kitchen-cooking.jpg", "kitchen cooking area", "kitchen appliances cabinets", 18),
    ("indoor/13-bathroom.jpg", "bathroom with toilet and sink", "bathroom toilet sink shower", 0),
    ("indoor/14-bathroom-sink.jpg", "bathroom sink and toiletries", "bathroom toilet sink shower", 3),
    ("indoor/15-bedroom.jpg", "bedroom with household furniture", "bedroom bed nightstand lamp", 0),
    ("indoor/16-bedroom-furniture.jpg", "bedroom furniture", "bedroom bed nightstand lamp", 3),
    ("indoor/17-office.jpg", "office desks and computers", "office computer workstations", 2),
    ("indoor/18-office-workspace.jpg", "office workspace", "office computer workstations", 6),
    ("indoor/19-classroom.jpg", "classroom with desks", "classroom desks chairs interior", 0),
    ("indoor/20-classroom-desks.jpg", "classroom desks and chairs", "classroom desks chairs interior", 2),
    ("indoor/21-supermarket.jpg", "supermarket aisle", "supermarket aisle shopping carts", 2),
    ("indoor/22-supermarket-cart.jpg", "supermarket with shopping carts", "supermarket aisle shopping carts", 3),
    ("indoor/23-restaurant.jpg", "restaurant dining room", "restaurant interior tables chairs", 0),
    ("indoor/24-restaurant-tables.jpg", "restaurant tables and chairs", "restaurant interior tables chairs", 3),
    ("indoor/25-living-room.jpg", "living room with sofa", "living room interior", 2),
    ("indoor/26-living-room-tv.jpg", "living room with television", "living room interior", 15),
    ("indoor/27-laundromat.jpg", "laundromat interior", "laundromat washing machines interior", 0),
    ("indoor/28-laundromat-machines.jpg", "laundromat washing machines", "laundromat washing machines interior", 3),
    ("indoor/29-workshop.jpg", "workshop with tools", "workbench hand tools workshop", 2),
    ("indoor/30-workshop-tools.jpg", "workshop tool area", "workbench hand tools workshop", 4),
    # Outdoor 11–30
    ("outdoor/11-crosswalk.jpg", "pedestrian crossing", "pedestrian crosswalk city street", 0),
    ("outdoor/12-crosswalk-street.jpg", "pedestrian crossing on a street", "pedestrian crosswalk city street", 3),
    ("outdoor/13-bus-stop.jpg", "bus stop", "bus stop shelter street", 0),
    ("outdoor/14-bus-shelter.jpg", "bus stop shelter", "bus stop shelter street", 3),
    ("outdoor/15-bicycle-parking.jpg", "bicycle parking", "bicycles parked rack street", 0),
    ("outdoor/16-bicycles-street.jpg", "parked bicycles on a street", "bicycles parked rack street", 3),
    ("outdoor/17-sidewalk.jpg", "city sidewalk", "city sidewalk pedestrians street", 0),
    ("outdoor/18-sidewalk-street.jpg", "sidewalk beside a street", "city sidewalk pedestrians street", 3),
    ("outdoor/19-playground.jpg", "playground equipment", "playground equipment city park", 0),
    ("outdoor/20-playground-park.jpg", "playground in a park", "playground equipment city park", 3),
    ("outdoor/21-fire-hydrant.jpg", "fire hydrant", "fire hydrant sidewalk street", 0),
    ("outdoor/22-fire-hydrant-sidewalk.jpg", "fire hydrant on a sidewalk", "fire hydrant sidewalk street", 3),
    ("outdoor/23-street-market.jpg", "street market", "street market stalls people", 0),
    ("outdoor/24-market-stalls.jpg", "street market stalls", "street market stalls people", 3),
    ("outdoor/25-car-park.jpg", "car park", "parking lot parked cars", 0),
    ("outdoor/26-parking-cars.jpg", "parking area with cars", "parking lot parked cars", 3),
    ("outdoor/27-mailbox.jpg", "mailbox", "street mailbox post box", 0),
    ("outdoor/28-mailbox-street.jpg", "mailbox beside a street", "street mailbox post box", 3),
    ("outdoor/29-picnic-table.jpg", "picnic table", "picnic table city park", 0),
    ("outdoor/30-picnic-table-park.jpg", "picnic table in a park", "picnic table city park", 3),
]


def _plain_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return " ".join(value.split())


def _search_files(query: str) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrsearch": f"{query} filemime:jpeg",
        "gsrlimit": "30",
        "prop": "info|imageinfo",
        "inprop": "url",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": "1280",
    }
    url = f"{_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            break
        except HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            time.sleep(2 ** (attempt + 1))
    time.sleep(0.4)

    candidates = []
    for page in payload.get("query", {}).get("pages", []):
        info = (page.get("imageinfo") or [{}])[0]
        metadata = info.get("extmetadata") or {}
        license_name = metadata.get("LicenseShortName", {}).get("value", "")
        mime = info.get("mime", "")
        categories = metadata.get("Categories", {}).get("value", "").lower()
        if _UNSUITABLE_TITLE.search(page["title"]):
            continue
        if any(
            marker in categories
            for marker in (
                "paintings",
                "drawings",
                "illustrations",
                "black and white photographs",
            )
        ):
            continue
        if not mime.startswith("image/") or mime == "image/svg+xml":
            continue
        if not license_name.startswith(_ALLOWED_LICENSE_PREFIXES):
            continue
        if min(int(info.get("width", 0)), int(info.get("height", 0))) < 480:
            continue
        candidates.append(
            {
                "title": page["title"],
                "source_page": page.get("canonicalurl") or page.get("fullurl"),
                "image_url": info.get("thumburl") or info["url"],
                "license": license_name,
                "license_url": metadata.get("LicenseUrl", {}).get("value", ""),
                "author": _plain_text(metadata.get("Artist", {}).get("value", "")),
            }
        )
    return candidates


def _download(url: str, target: Path) -> None:
    if target.exists():
        with Image.open(target) as image:
            image.verify()
        return
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            break
        except (HTTPError, TimeoutError, URLError) as exc:
            if (
                isinstance(exc, HTTPError)
                and exc.code != 429
            ) or attempt == 5:
                raise
            time.sleep(2 ** (attempt + 1))
    time.sleep(2.5)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    with Image.open(target) as image:
        image.verify()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--select-only",
        action="store_true",
        help="Print deterministic selections without downloading or editing.",
    )
    args = parser.parse_args()

    selections = []
    used_titles = set()
    if _CACHE_PATH.exists():
        search_cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    else:
        search_cache = {}
    for file, scene, query, offset in _TARGETS:
        if query not in search_cache:
            search_cache[query] = _search_files(query)
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_PATH.write_text(
                json.dumps(search_cache, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        candidates = [
            candidate
            for candidate in search_cache[query]
            if candidate["title"] not in used_titles
        ]
        if len(candidates) <= offset:
            raise RuntimeError(
                f"not enough usable Commons search results for {query!r}"
            )
        selected = candidates[offset]
        used_titles.add(selected["title"])
        item = {"file": file, "scene": scene, **selected}
        if not (_GALLERY / file).exists():
            item["image_url"] = (
                "https://commons.wikimedia.org/w/thumb.php?"
                + urllib.parse.urlencode(
                    {
                        "f": item["title"].removeprefix("File:"),
                        "w": "960",
                    }
                )
            )
        selections.append(item)
        print(f"{file:42} {selected['title']}")

    if args.select_only:
        return

    for item in selections:
        _download(item["image_url"], _GALLERY / item["file"])

    manifest_path = _GALLERY / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    replacing = {item["file"] for item in selections}
    retained = [item for item in manifest["items"] if item["file"] not in replacing]
    manifest["updated"] = "2026-07-30"
    manifest["items"] = sorted(
        retained + selections,
        key=lambda item: (
            0 if item["file"].startswith("indoor/") else 1,
            item["file"],
        ),
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
