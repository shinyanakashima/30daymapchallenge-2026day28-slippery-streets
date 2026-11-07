"""Winter-solstice sunlight on Sapporo's central streets, from PLATEAU building heights.

Outputs (web/data/):
  roads.geojson       road surfaces with mean sunlit minutes and share never sunlit
  buildings.geojson   building footprints in the study area
  sun_grid.png        2 m sunlight grid on road surfaces (image overlay)
  shadows/HHMM.geojson  building shadows for the time slider
  summary.json        totals and sun positions
"""
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pvlib
import shapely
from PIL import Image
from rasterio import features
from rasterio.transform import from_origin
from pyproj import Transformer
from shapely.geometry import box

from config import (CASTER_MARGIN_M, CENTER_LONLAT, CRS_METRIC, DATE, FRAME_STEP_MIN,
                    GRID_M, HALF_SIZE_M, OSM_JSON, OUT, STEP_MIN, STOREY_HEIGHT_M, TZ, WORK)

to_metric = Transformer.from_crs("EPSG:4326", CRS_METRIC, always_xy=True)


def study_box():
    cx, cy = to_metric.transform(*CENTER_LONLAT)
    return box(cx - HALF_SIZE_M, cy - HALF_SIZE_M, cx + HALF_SIZE_M, cy + HALF_SIZE_M)


# ---------------------------------------------------------------- inputs
def load_buildings(area):
    cols = ["id", "measuredHeight", "storeysAboveGround"]
    b = gpd.read_file(WORK / "bldg.gpkg", layer="bldg:Building", columns=cols)
    b = b.set_crs(CRS_METRIC, allow_override=True)
    b["geometry"] = shapely.force_2d(b.geometry.values)
    b = b[b.intersects(area.buffer(CASTER_MARGIN_M))].copy()
    h = b["measuredHeight"].where(b["measuredHeight"] > 0)
    storeys = b["storeysAboveGround"].where(b["storeysAboveGround"] > 0)
    b["height_src"] = np.where(h.notna(), "measured", np.where(storeys.notna(), "storeys", "none"))
    b["height"] = h.fillna(storeys * STOREY_HEIGHT_M)
    stats = b["height_src"].value_counts().to_dict()
    b = b[b["height"].notna()].copy()
    b["geometry"] = shapely.make_valid(b.geometry.values)
    b = b.explode(index_parts=False)
    b = b[b.geom_type == "Polygon"].reset_index(drop=True)
    return b, stats


def load_roads(area):
    t = gpd.read_file(WORK / "tran.gpkg", layer="tran:Road", columns=["id", "function"])
    t = t.set_crs(CRS_METRIC, allow_override=True)
    t["geometry"] = shapely.make_valid(shapely.force_2d(t.geometry.values))
    t = t[t.intersects(area)].copy()
    t["geometry"] = t.geometry.intersection(area)
    t["geometry"] = t.geometry.apply(lambda g: shapely.union_all(
        [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon"]))
    t = t[~t.geometry.is_empty & (t.geometry.area > 1.0)].reset_index(drop=True)
    t["function"] = t["function"].fillna("").str.strip('[]"')
    return t


def attach_osm_names(roads):
    data = json.loads(Path(OSM_JSON).read_text())
    rows = []
    skip = {"footway", "steps", "path", "cycleway", "corridor", "elevator", "platform",
            "construction", "proposed", "bus_stop", "pedestrian_area"}
    for el in data["elements"]:
        tags = el.get("tags", {})
        if el.get("type") != "way" or "geometry" not in el or tags.get("highway") in skip:
            continue
        name = tags.get("name")
        if not name:
            continue
        xs, ys = to_metric.transform([p["lon"] for p in el["geometry"]],
                                     [p["lat"] for p in el["geometry"]])
        if len(xs) < 2:
            continue
        rows.append({"name_ja": name, "name_en": tags.get("name:en", ""),
                     "geometry": shapely.LineString(np.c_[xs, ys])})
    osm = gpd.GeoDataFrame(rows, crs=CRS_METRIC)
    pairs = gpd.sjoin(roads[["geometry"]], osm, predicate="intersects", how="inner")
    pairs["len"] = [roads.geometry.iloc[i].intersection(osm.geometry.iloc[j]).length
                    for i, j in zip(pairs.index, pairs["index_right"])]
    best = pairs.sort_values("len", ascending=False).groupby(level=0).first()
    best = best[best["len"] > 3.0]
    roads["name_ja"] = best["name_ja"].reindex(roads.index).fillna("")
    roads["name_en"] = best["name_en"].reindex(roads.index).fillna("")
    return roads


# ---------------------------------------------------------------- sun
def sun_positions(lon, lat):
    times = pd.date_range(f"{DATE} 00:00", f"{DATE} 23:59", freq=f"{STEP_MIN}min", tz=TZ)
    sp = pvlib.solarposition.get_solarposition(times, lat, lon, altitude=20)
    sp = sp[sp["apparent_elevation"] > 0]
    sun = pvlib.solarposition.sun_rise_set_transit_spa(
        pd.DatetimeIndex([pd.Timestamp(f"{DATE} 12:00", tz=TZ)]), lat, lon)
    return sp, sun.iloc[0]


# ---------------------------------------------------------------- shadows
def building_rings(b):
    """Exterior ring vertices per building (closed, as arrays)."""
    rings = [np.asarray(g.exterior.coords)[:, :2] for g in b.geometry]
    return rings


def shadow_parts(b, rings, azimuth_deg, elevation_deg):
    """Shadow pieces for every building at one sun position.

    A flat-roofed prism casts the footprint swept along the vector
    d = -height / tan(elevation) * (sin az, cos az). The swept area is the union of the
    footprint, the translated footprint, and one parallelogram per wall edge.
    """
    az = np.radians(azimuth_deg)
    L = b["height"].to_numpy() / np.tan(np.radians(elevation_deg))
    dx, dy = -L * np.sin(az), -L * np.cos(az)

    counts = np.array([len(r) - 1 for r in rings])
    p = np.concatenate([r[:-1] for r in rings])
    q = np.concatenate([r[1:] for r in rings])
    ddx = np.repeat(dx, counts)
    ddy = np.repeat(dy, counts)
    quads = np.stack([p, q, q + np.c_[ddx, ddy], p + np.c_[ddx, ddy], p], axis=1)
    edge_polys = shapely.polygons(quads)
    # translated footprint (exterior ring only; holes are covered by the wall pieces)
    offs = np.repeat(np.c_[dx, dy], counts + 1, axis=0)
    moved = shapely.polygons(shapely.linearrings(np.concatenate(rings) + offs,
                                                 indices=np.repeat(np.arange(len(rings)), counts + 1)))
    parts = np.concatenate([b.geometry.values, moved, edge_polys])
    parts = parts[shapely.area(parts) > 1e-6]
    return parts


def shaded_raster(parts, shape, transform):
    """True where the grid-cell centre lies inside any shadow piece."""
    return features.rasterize(((g, 1) for g in parts), out_shape=shape, transform=transform,
                              fill=0, dtype="uint8").astype(bool)


def shadow_union(parts, area):
    clip = area.buffer(50)
    tree = shapely.STRtree(parts)
    sel = parts[tree.query(clip, predicate="intersects")]
    sel = shapely.intersection(sel, clip)
    u = shapely.union_all(sel[~shapely.is_empty(sel)], grid_size=0.01)
    return u.simplify(0.4)


# ---------------------------------------------------------------- output helpers
def write_geojson(gdf, path, props, precision=6):
    g = gdf.to_crs("EPSG:4326")
    g["geometry"] = shapely.set_precision(g.geometry.values, 10 ** -precision)
    g = g[~g.geometry.is_empty]
    g[props + ["geometry"]].to_file(path, driver="GeoJSON", COORDINATE_PRECISION=precision)


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "shadows").mkdir(exist_ok=True)
    area = study_box()
    b, hstats = load_buildings(area)
    roads = attach_osm_names(load_roads(area))
    print(f"buildings {len(b)} {hstats}, roads {len(roads)}  ({time.time()-t0:.0f}s)")

    # grid of 2 m cell centres over the square; keep the ones on road surfaces
    minx, miny, maxx, maxy = area.bounds
    nx, ny = int(round((maxx - minx) / GRID_M)), int(round((maxy - miny) / GRID_M))
    transform = from_origin(minx, maxy, GRID_M, GRID_M)  # row 0 = north
    road_id = features.rasterize(((g, i + 1) for i, g in enumerate(roads.geometry.values)),
                                 out_shape=(ny, nx), transform=transform, fill=0,
                                 dtype="int32").ravel()
    pi = np.flatnonzero(road_id)
    ri = road_id[pi] - 1
    print(f"road cells {len(pi)}  ({time.time()-t0:.0f}s)")

    sp, sun = sun_positions(*CENTER_LONLAT)
    rings = building_rings(b)
    sun_min = np.zeros(len(pi), dtype=np.int32)
    frames = []
    for ts, row in sp.iterrows():
        parts = shadow_parts(b, rings, row["azimuth"], row["apparent_elevation"])
        shaded = shaded_raster(parts, (ny, nx), transform).ravel()[pi]
        sun_min[~shaded] += STEP_MIN
        label = ts.strftime("%H%M")
        if ts.minute % FRAME_STEP_MIN == 0:
            u = shadow_union(parts, area)
            gdf = gpd.GeoDataFrame({"t": [label]}, geometry=[u], crs=CRS_METRIC)
            write_geojson(gdf, OUT / "shadows" / f"{label}.geojson", ["t"])
            frames.append(label)
        print(f"{label} az={row['azimuth']:.1f} el={row['apparent_elevation']:.2f} "
              f"shaded={shaded.mean():.3f}  ({time.time()-t0:.0f}s)")

    # per-road statistics
    df = pd.DataFrame({"road": ri, "sun": sun_min, "dark": sun_min == 0})
    agg = df.groupby("road").agg(sun_mean=("sun", "mean"), dark_share=("dark", "mean"),
                                 cells=("sun", "size"))
    roads = roads.join(agg)
    roads = roads[roads["cells"].notna()].copy()
    roads["sun_min"] = roads["sun_mean"].round(0).astype(int)
    roads["dark_pct"] = (roads["dark_share"] * 100).round(1)
    roads["area_m2"] = roads.geometry.area.round(0).astype(int)
    write_geojson(roads, OUT / "roads.geojson",
                  ["id", "name_ja", "name_en", "function", "sun_min", "dark_pct", "area_m2"])

    inside = b[b.intersects(area)].copy()
    inside["geometry"] = inside.geometry.intersection(area).simplify(0.2)
    inside["h"] = inside["height"].round(1)
    write_geojson(inside, OUT / "buildings.geojson", ["h"])

    # sunlight grid image (RGBA, transparent off-road); value encoded in R, alpha marks road
    grid = np.full(nx * ny, -1, dtype=np.int32)
    grid[pi] = sun_min
    grid = grid.reshape(ny, nx)
    np.save(WORK / "sun_grid.npy", grid)
    day_len = int(len(sp) * STEP_MIN)
    write_grid_png(grid, day_len, OUT / "sun_grid.png")

    to_ll = Transformer.from_crs(CRS_METRIC, "EPSG:4326", always_xy=True)
    corners = [to_ll.transform(x, y) for x, y in
               [(minx, maxy), (maxx, maxy), (maxx, miny), (minx, miny)]]
    dark_share = float((sun_min == 0).mean())
    summary = {
        "date": DATE,
        "timezone": TZ,
        "center": CENTER_LONLAT,
        "half_size_m": HALF_SIZE_M,
        "grid_m": GRID_M,
        "step_min": STEP_MIN,
        "possible_sun_min": day_len,
        "sunrise": sun["sunrise"].strftime("%H:%M"),
        "sunset": sun["sunset"].strftime("%H:%M"),
        "transit": sun["transit"].strftime("%H:%M"),
        "max_elevation": round(float(sp["apparent_elevation"].max()), 1),
        "road_area_m2": int(len(pi) * GRID_M * GRID_M),
        "never_sunlit_share": round(dark_share, 4),
        "mean_sun_min": round(float(sun_min.mean()), 1),
        "frames": frames,
        "grid_corners": corners,
        "buildings_used": int(len(b)),
        "height_source_counts": {k: int(v) for k, v in hstats.items()},
        "roads": int(len(roads)),
        "bbox": [min(c[0] for c in corners), min(c[1] for c in corners),
                 max(c[0] for c in corners), max(c[1] for c in corners)],
        "sun": [{"t": ts.strftime("%H:%M"), "az": round(float(r["azimuth"]), 2),
                 "el": round(float(r["apparent_elevation"]), 2)} for ts, r in sp.iterrows()],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "sun"}, ensure_ascii=False))
    print(f"done ({time.time()-t0:.0f}s)")


# colour ramp shared with the web map (minutes of sun -> colour)
RAMP = [(0, (143, 227, 255)), (1, (92, 84, 128)), (60, (146, 94, 132)),
        (150, (214, 122, 104)), (300, (242, 170, 82)), (480, (255, 224, 138))]


def ramp_color(v):
    if v <= 0:
        return RAMP[0][1]
    for (a, ca), (b, cb) in zip(RAMP[1:], RAMP[2:]):
        if v <= b:
            t = (v - a) / (b - a)
            return tuple(int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3))
    return RAMP[-1][1]


def write_grid_png(grid, day_len, path):
    lut = np.array([ramp_color(v) for v in range(day_len + 1)], dtype=np.uint8)
    rgba = np.zeros(grid.shape + (4,), dtype=np.uint8)
    on = grid >= 0
    rgba[on, :3] = lut[np.clip(grid[on], 0, day_len)]
    rgba[on, 3] = 255
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


if __name__ == "__main__":
    main()
