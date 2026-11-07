"""Shared settings for the preprocessing scripts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Raw downloads and intermediate files live outside git (see .gitignore).
WORK = ROOT / "work"
RAW = WORK / "plateau_raw"
OUT = ROOT / "web" / "data"

# PLATEAU Sapporo (01100), FY2020 model, CityGML v4 package (spec 4.1, registered 2024)
PLATEAU_ZIP_URL = (
    "https://assets.cms.plateau.reearth.io/assets/be/3b8cfb-5459-4f9d-b08c-fb4ab72fbdbd/"
    "01100_sapporo-shi_city_2020_citygml_7_op.zip"
)
PLATEAU_DATASET_PAGE = "https://www.geospatial.jp/ckan/dataset/plateau-01100-sapporo-shi-2020"

# 3rd-level mesh codes covering the study area plus a ~1 km margin for shadow casters
MESHES = [f"644142{a}{b}" for a in range(4, 10) for b in range(5, 10)] + [
    f"644143{a}0" for a in range(4, 10)
]

# Study area: 3 km x 3 km square around Odori - Susukino, in JGD2011 / Japan Plane
# Rectangular CS XII (EPSG:6680).
CRS_METRIC = "EPSG:6680"
CENTER_LONLAT = (141.3530, 43.0575)
HALF_SIZE_M = 1500.0
CASTER_MARGIN_M = 1000.0  # buildings this far outside the square still cast shadows into it

# Sun
DATE = "2026-12-22"
TZ = "Asia/Tokyo"
STEP_MIN = 10
FRAME_STEP_MIN = 30  # shadow frames for the time slider

# Sunlight grid
GRID_M = 2.0

# Height fallback for buildings without measuredHeight
STOREY_HEIGHT_M = 3.0

OSM_JSON = WORK / "osm_raw" / "highways.json"
OVERPASS_URL = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
