"""Cross-check the shadow geometry against pybdshadow on a sub-area.

  python validate.py prepare     # main env: export buildings + our shadows
  <py3.9 env>/python pybdshadow_run.py
  python validate.py compare     # main env: IoU / area ratio per time
"""
import json
import sys

import geopandas as gpd
import pandas as pd
import pvlib
import shapely
from pyproj import Transformer
from shapely.geometry import box

from compute import load_buildings, shadow_parts, study_box
from config import CENTER_LONLAT, CRS_METRIC, DATE, TZ, WORK

VDIR = WORK / "validate"
HALF = 400.0     # 800 m x 800 m test square
MARGIN = 600.0   # casters around it
TIMES = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]


def test_box():
    cx, cy = Transformer.from_crs("EPSG:4326", CRS_METRIC, always_xy=True).transform(*CENTER_LONLAT)
    return box(cx - HALF, cy - HALF, cx + HALF, cy + HALF)


def prepare():
    VDIR.mkdir(parents=True, exist_ok=True)
    tb = test_box()
    b, _ = load_buildings(study_box())
    b = b[b.intersects(tb.buffer(MARGIN))].reset_index(drop=True)
    b["building_id"] = range(len(b))
    b[["building_id", "height", "geometry"]].to_crs("EPSG:4326").to_file(
        VDIR / "buildings.geojson", driver="GeoJSON")
    rings = [shapely.get_coordinates(g.exterior) for g in b.geometry]
    lon, lat = CENTER_LONLAT
    rows = []
    for t in TIMES:
        ts = pd.Timestamp(f"{DATE} {t}", tz=TZ)
        sp = pvlib.solarposition.get_solarposition(pd.DatetimeIndex([ts]), lat, lon, altitude=20).iloc[0]
        parts = shadow_parts(b, rings, sp["azimuth"], sp["apparent_elevation"])
        u = shapely.union_all(parts, grid_size=0.01).intersection(tb)
        rows.append({"t": t, "az": sp["azimuth"], "el": sp["apparent_elevation"], "geometry": u})
    gpd.GeoDataFrame(rows, crs=CRS_METRIC).to_file(VDIR / "ours.gpkg")
    print("prepared", len(b), "buildings")


def compare():
    tb = test_box()
    ours = gpd.read_file(VDIR / "ours.gpkg")
    theirs = gpd.read_file(VDIR / "pybdshadow.gpkg").to_crs(CRS_METRIC)
    out = []
    for _, o in ours.iterrows():
        th = theirs[theirs["t"] == o["t"]].iloc[0]
        a = o.geometry
        b = shapely.make_valid(th.geometry).intersection(tb)
        inter = a.intersection(b).area
        uni = a.union(b).area
        out.append({
            "time": o["t"],
            "sun_el_pvlib": round(o["el"], 2), "sun_el_suncalc": round(th["el"], 2),
            "sun_az_pvlib": round(o["az"], 2), "sun_az_suncalc": round(th["az"], 2),
            "shadow_share_ours": round(a.area / tb.area, 4),
            "shadow_share_pybdshadow": round(b.area / tb.area, 4),
            "iou": round(inter / uni, 4),
        })
    df = pd.DataFrame(out)
    print(df.to_string(index=False))
    (VDIR / "result.json").write_text(json.dumps(out, indent=1))
    print("mean IoU", round(df["iou"].mean(), 4), "min IoU", df["iou"].min())


if __name__ == "__main__":
    {"prepare": prepare, "compare": compare}[sys.argv[1]]()
