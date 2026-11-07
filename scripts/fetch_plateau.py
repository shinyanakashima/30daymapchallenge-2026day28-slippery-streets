"""Download only the bldg / tran CityGML tiles needed for the study area.

The PLATEAU Sapporo package is ~2.7 GB, so files are read out of the remote zip
with HTTP range requests instead of downloading the whole archive.
"""
import os

from remotezip import RemoteZip

from config import MESHES, PLATEAU_ZIP_URL, RAW


def main():
    root = RAW / "01100_sapporo-shi_city_2020_citygml_7_op"
    targets = {f"udx/{t}/{m}_{t}_6697_op.gml" for m in MESHES for t in ("bldg", "tran")}
    with RemoteZip(PLATEAU_ZIP_URL) as z:
        names = [n for n in z.namelist() if n in targets or n.startswith("codelists/")]
        for n in names:
            if n.endswith("/"):
                continue
            p = root / n
            if p.exists() and p.stat().st_size == z.getinfo(n).file_size:
                continue
            z.extract(n, root)
            print("extracted", n)
    missing = targets - set(names)
    if missing:
        print("not in archive:", sorted(missing))


if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    main()
