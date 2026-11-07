#!/usr/bin/env bash
# Convert PLATEAU CityGML to GeoPackage with PLATEAU GIS Converter (CLI "nusamai").
# NUSAMAI points to the CLI binary built from
# https://github.com/Project-PLATEAU/PLATEAU-GIS-Converter (cargo build --release -p nusamai).
set -euo pipefail
cd "$(dirname "$0")/.."
NUSAMAI="${NUSAMAI:-nusamai}"
SRC=work/plateau_raw/01100_sapporo-shi_city_2020_citygml_7_op/udx

# EPSG:6680 = JGD2011 / Japan Plane Rectangular CS XII (Hokkaido central).
# use_lod=min_lod picks the footprint (LOD0) of each building and the LOD1 road surface.
"$NUSAMAI" "$SRC/bldg/*.gml" --sink gpkg --output work/bldg.gpkg --epsg 6680 -t use_lod=min_lod
"$NUSAMAI" "$SRC/tran/*.gml" --sink gpkg --output work/tran.gpkg --epsg 6680 -t use_lod=min_lod
