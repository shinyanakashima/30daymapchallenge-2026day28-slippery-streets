"""Fetch OpenStreetMap highway lines (used only to attach street names)."""
import json
import os
import urllib.parse
import urllib.request

from config import OSM_JSON, OVERPASS_URL

QUERY = '[out:json][timeout:120];way["highway"](43.035,141.32,43.08,141.385);out tags geom;'


def main():
    os.makedirs(OSM_JSON.parent, exist_ok=True)
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    with urllib.request.urlopen(OVERPASS_URL, data=data, timeout=180) as r:
        body = r.read()
    json.loads(body)
    OSM_JSON.write_bytes(body)
    print("saved", OSM_JSON, len(body))


if __name__ == "__main__":
    main()
