"""Run pybdshadow (Python 3.9 environment) on the buildings exported by validate.py."""
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pybdshadow
from suncalc import get_position
from shapely.ops import unary_union

VDIR = Path(__file__).resolve().parents[1] / "work" / "validate"
DATE = "2026-12-22"
TIMES = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]

b = gpd.read_file(VDIR / "buildings.geojson")
rows = []
for t in TIMES:
    date = pd.to_datetime(f"{DATE} {t}").tz_localize("Asia/Tokyo").tz_convert("UTC")
    shadows = pybdshadow.bdshadow_sunlight(b, date, height="height", roof=False, include_building=True)
    lon, lat = 141.3530, 43.0575
    pos = get_position(date, lon, lat)
    # suncalc azimuth is measured from south, clockwise towards west
    az = (math.degrees(pos["azimuth"]) + 180.0) % 360.0
    el = math.degrees(pos["altitude"])
    rows.append({"t": t, "az": az, "el": el, "geometry": unary_union(list(shadows.geometry))})
    print(t, round(az, 2), round(el, 2), len(shadows))
gpd.GeoDataFrame(rows, crs="EPSG:4326").to_file(VDIR / "pybdshadow.gpkg", driver="GPKG")
