#!/usr/bin/env python
##############################################################################
# MODULE:    i.hyper.lib_zenodo
# AUTHOR(S): Spectral Feature Extraction and Interpretation Engine
# PURPOSE:   Harvest curated spectral libraries published on Zenodo into the
#            shared, source-tagged, partitioned local spectral database used
#            by i.hyper.lib_ecosis, i.hyper.lib_gsti, i.hyper.lib_relab and
#            i.hyper.lib_usgs, usable by any i.hyper.* module.
#
#            Zenodo is where the regional spectral libraries live. The five
#            sources already harvested are global or North American, and
#            between them they hold almost no Mediterranean vegetation: a
#            search of the local store for the species of a Provence site
#            returned four spectra of Quercus ilex, twenty of Quercus
#            pubescens and ten of Laurus nobilis, and nothing at all for
#            Pinus halepensis, Olea europaea, Cupressus, Juniperus, Pistacia,
#            Arbutus unedo, Cistus or Rosmarinus. Matching a Mediterranean
#            canopy against that is matching against the wrong flora, and it
#            returns a confident wrong answer rather than no answer.
#
#            Zenodo has no single spectral schema, so each dataset is read by
#            its own reader and listed in a registry with its record id,
#            licence and citation. Adding a library means adding a registry
#            entry and a reader, not rewriting the harvester.
# SPDX-License-Identifier: Unlicense
##############################################################################

# %module
# % description: Harvest curated spectral libraries published on Zenodo into the shared local spectral database used by i.hyper.* modules
# % keyword: imagery
# % keyword: hyperspectral
# % keyword: spectral library
# % keyword: Zenodo
# % keyword: Mediterranean
# %end

# %option
# % key: dataset
# % type: string
# % required: no
# % multiple: yes
# % description: Registry key(s) of the dataset(s) to harvest (default: all). Use the -l flag to list them with their species, licence and citation
# % guisection: Input
# %end

# %option
# % key: record
# % type: string
# % required: no
# % multiple: yes
# % description: Zenodo record id(s) to harvest instead of a registry key. Only records whose format one of the readers understands can be harvested
# % guisection: Input
# %end

# %option G_OPT_M_DIR
# % key: cache_dir
# % required: no
# % description: Directory for the downloaded Zenodo files (default: $HOME/grassdata/hyperspeclib/_cache/zenodo). Files already present are reused
# % guisection: Input
# %end

# %option
# % key: output
# % type: string
# % required: no
# % description: Shared spectral library root directory (default: $HOME/grassdata/hyperspeclib -- the same fixed location used by the other i.hyper.lib_* harvesters)
# % guisection: Output
# %end

# %option
# % key: format
# % type: string
# % required: no
# % options: parquet,sqlite
# % answer: parquet
# % description: Storage backend. parquet supports fast partitioned/parallel columnar access; sqlite is a zero-extra-dependency fallback
# % guisection: Output
# %end

# %flag
# % key: l
# % description: List the registry and exit without downloading anything
# %end

# %flag
# % key: n
# % description: Report what would be harvested without writing to the store
# %end

# %flag
# % key: f
# % description: Re-harvest a dataset already recorded in the manifest
# %end

import datetime as dt
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import grass.script as gs

SOURCE_DATABASE = "zenodo"
MANIFEST_NAME = "_manifest.json"
ZENODO_API = "https://zenodo.org/api/records"
DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), "grassdata",
                            "hyperspeclib")

# The registry. Every entry names the record, the reader that understands its
# layout, and the licence under which it may be redistributed, because a
# harvest that loses the licence makes the store unusable downstream. The
# species list is what the dataset actually contains, verified against its own
# metadata rather than copied from its abstract.
REGISTRY = {
    "mediterranean_woodlands": {
        "record": "5176824",
        "title": "Spectral library of vegetation from Mediterranean woodlands",
        "reader": "specveg",
        "licence": "CC-BY-4.0",
        "site": "Herdade da Machoqueira do Grou, Central Portugal",
        "instrument": "ASD FieldSpec3",
        "range_nm": [350, 2300],
        "species": ["Quercus suber", "Cistus salviifolius", "Ulex europaeus",
                    "C3 grass mixture"],
        "note": ("974 of its 1216 observations are canopy rather than leaf "
                 "measurements, which is what makes it worth harvesting: a "
                 "drone crown is a canopy, and a laboratory leaf spectrum is "
                 "not comparable to one."),
        "files": ["specveg_data_spectra.txt", "specveg_metadata.txt"],
    },
    "montesinho": {
        "record": "10798148",
        "title": ("Spectral library of plant species from Montesinho Natural "
                  "Park in Portugal"),
        "reader": "montesinho",
        "licence": "CC-BY-4.0",
        "site": "Montesinho Natural Park, north-east Portugal",
        "instrument": "ASD FieldSpec (350-2500 nm)",
        "range_nm": [350, 2500],
        "species": ["Quercus rotundifolia", "Quercus pyrenaica",
                    "Arbutus unedo", "Cistus ladanifer", "Erica arborea",
                    "Castanea sativa", "Fraxinus angustifolia",
                    "Crataegus monogyna", "Alnus glutinosa",
                    "Frangula alnus", "Cytisus multiflorus",
                    "Genista falcata", "Acacia dealbata",
                    "Dactylis glomerata", "Trifolium repens"],
        "note": ("Leaf level. Quercus rotundifolia is the Iberian holm oak "
                 "of the Quercus ilex complex, the nearest reference this "
                 "harvest can offer to a Provence holm oak."),
        "files": ["Spectrum.zip"],
    },
}

# Montesinho names its files by a six to seven letter species code. The codes
# are not documented in the archive itself, so they are resolved here from the
# species list of the dataset report, and an unknown code is reported rather
# than guessed at.
MONTESINHO_CODES = {
    "AcaDea": "Acacia dealbata",
    "AlnGlu": "Alnus glutinosa",
    "ArbUne": "Arbutus unedo",
    "CastSat": "Castanea sativa",
    "CistLad": "Cistus ladanifer",
    "CratMon": "Crataegus monogyna",
    "CytiMul": "Cytisus multiflorus",
    "DactGlo": "Dactylis glomerata",
    "EriArb": "Erica arborea",
    "FranAln": "Frangula alnus",
    "FraxAng": "Fraxinus angustifolia",
    "GenFal": "Genista falcata",
    "QuerPyr": "Quercus pyrenaica",
    "QuerRot": "Quercus rotundifolia",
    "TrifRep": "Trifolium repens",
}

# The Mediterranean woodlands dataset writes one non-taxon into its genus
# column: "c3mixture", a mixed C3 herbaceous sward rather than a species. It is
# renamed here so the material name reads as what it is, and flagged as not a
# taxon, because a mixture must not be matched against as though it named a
# plant. Its own common_name column says "Herbaceous species".
SPECVEG_NON_TAXA = {"c3mixture": "C3 grass mixture"}

_PARQUET_SCHEMA_FIELDS = [
    ("source_database", "string"),
    ("dataset_id", "string"),
    ("dataset_title", "string"),
    ("record_id", "string"),
    ("organization", "string"),
    ("source_url", "string"),
    ("source_api_url", "string"),
    ("longitude", "double"),
    ("latitude", "double"),
    ("measurement_type", "string"),
    ("wavelength_unit", "string"),
    ("n_bands", "int32"),
    ("wavelengths", "list<double>"),
    ("values", "list<double>"),
    ("extra_metadata", "string"),
    ("ingest_date", "string"),
]


# ---------------------------------------------------------------------------
# Zenodo access
# ---------------------------------------------------------------------------

def api_record(record_id):
    """Fetch one Zenodo record's metadata."""
    url = f"{ZENODO_API}/{record_id}"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        gs.fatal(_("Cannot reach Zenodo record {rid}: {err}").format(
            rid=record_id, err=exc))
    return None


def fetch_file(record, key, cache_dir):
    """Download one file of a record, or reuse the cached copy.

    The size is checked against what Zenodo reports, because a truncated
    download is otherwise indistinguishable from a short file and would be
    parsed into a silently incomplete library.
    """
    entry = next((f for f in record.get("files", [])
                  if f.get("key") == key), None)
    if entry is None:
        gs.fatal(_("Record {rid} has no file named <{key}>").format(
            rid=record.get("id"), key=key))
    target = os.path.join(cache_dir, key)
    expect = int(entry.get("size") or 0)
    if os.path.exists(target) and (not expect
                                   or os.path.getsize(target) == expect):
        gs.verbose(_("Reusing cached <{key}>").format(key=key))
        return target
    url = entry.get("links", {}).get("self") or (
        f"{ZENODO_API}/{record['id']}/files/{key}/content")
    gs.message(_("Downloading {key} ({mb:.1f} MB)...").format(
        key=key, mb=expect / 1e6 if expect else 0.0))
    os.makedirs(cache_dir, exist_ok=True)
    tmp = target + ".part"
    try:
        with urllib.request.urlopen(url, timeout=600) as resp, \
                open(tmp, "wb") as handle:
            done = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if expect:
                    gs.percent(done, expect, 2)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        gs.fatal(_("Download of <{key}> failed: {err}").format(
            key=key, err=exc))
    if expect and os.path.getsize(tmp) != expect:
        os.unlink(tmp)
        gs.fatal(_("Download of <{key}> is incomplete; expected {n} bytes")
                 .format(key=key, n=expect))
    Path(tmp).replace(target)
    return target


# ---------------------------------------------------------------------------
# Readers. Each yields row dicts in the shared schema.
# ---------------------------------------------------------------------------

def _strip_header(path):
    """Yield the data lines of a file whose header is '#' commented."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("#"):
                yield line


def read_specveg(entry, record, paths):
    """Read the Mediterranean woodlands library (record 5176824).

    The spectra arrive in long form, one row per wavelength per observation,
    so they are accumulated by observation and emitted when the observation
    changes. The species lives in a separate metadata table joined on
    observation_ID.
    """
    import csv
    meta_path = paths["specveg_metadata.txt"]
    spectra_path = paths["specveg_data_spectra.txt"]
    meta, by_target = {}, {}
    for row in csv.DictReader(_strip_header(meta_path)):
        obs = (row.get("observation_ID") or "").strip()
        if obs:
            meta[obs] = row
        # The ID column names the physical target ("fsb01"), which is sampled
        # on several dates. Species and measurement level are constant per ID
        # across all 27 of them, so it is a sound fallback for an observation
        # the metadata table omits -- the 2012-03-10 session is missing from
        # it entirely, although its six spectra are in the data file.
        tid = (row.get("ID") or "").strip()
        if tid:
            by_target.setdefault(tid, row)
    gs.message(_("{n} observations described in the metadata table")
               .format(n=len(meta)))

    current, waves, vals = None, [], []
    seen = 0
    recovered, unnamed = [], []

    def finish(obs):
        nonlocal seen
        if not obs or not waves:
            return None
        info = meta.get(obs)
        source = "observation_ID"
        if info is None:
            # Fall back to the target ID, and say so on the row.
            info = by_target.get(obs.rsplit("_", 1)[0], {})
            source = "ID" if info else "none"
            (recovered if info else unnamed).append(obs)
        genus = (info.get("species_genus") or "").strip()
        specific = (info.get("species_specific") or "").strip()
        species = " ".join(p for p in (genus, specific) if p and p != "NA")
        is_taxon = species.lower() not in SPECVEG_NON_TAXA
        species = SPECVEG_NON_TAXA.get(species.lower(), species)
        seen += 1
        return build_row(
            entry, record, record_id=obs,
            wavelengths=list(waves), values=list(vals),
            species=species or None,
            extra={
                "species": species or None,
                "species_source": source,
                "is_taxon": is_taxon,
                "vegetation_type": info.get("vegetation_type"),
                "measurement_level": info.get("description"),
                "common_name": info.get("species_common_name"),
                "collection_date": info.get("collection_date"),
                "instrument": info.get("instrument"),
                "replicate": info.get("replicate"),
                "target_id": info.get("target_ID"),
                "photo_url": info.get("URL"),
                "recorded_by": info.get("recorded_by"),
            },
            longitude=_as_float(info.get("longitude")),
            latitude=_as_float(info.get("latitude")),
        )

    for row in csv.DictReader(_strip_header(spectra_path)):
        obs = (row.get("observation_ID") or "").strip()
        if obs != current:
            built = finish(current)
            if built is not None:
                yield built
            current, waves, vals = obs, [], []
        wave = _as_float(row.get("wavelength"))
        value = _as_float(row.get("R"))
        if wave is not None and value is not None:
            waves.append(wave)
            vals.append(value)
    built = finish(current)
    if built is not None:
        yield built
    if recovered:
        gs.warning(_("{n} observations are absent from the metadata table; "
                     "their species was taken from the target ID instead "
                     "({ids}). This is recorded as species_source=ID on "
                     "each row.").format(n=len(recovered),
                                         ids=", ".join(recovered[:8])))
    if unnamed:
        gs.warning(_("{n} observations have neither a metadata row nor a "
                     "known target ID and are stored without a species "
                     "({ids})").format(n=len(unnamed),
                                       ids=", ".join(unnamed[:8])))


def read_montesinho(entry, record, paths):
    """Read the Montesinho library (record 10798148).

    The archive holds one two-column CSV per measured leaf, named
    <SpeciesCode>_<leaf>_<grid>_<plot>[_side].csv, with a title line and a
    column header before the data.
    """
    archive = paths["Spectrum.zip"]
    with zipfile.ZipFile(archive) as zf:
        members = sorted(n for n in zf.namelist() if n.lower().endswith(".csv"))
        unknown = set()
        for i, name in enumerate(members, start=1):
            gs.percent(i, len(members), 2)
            stem = os.path.splitext(os.path.basename(name))[0]
            code = stem.split("_")[0]
            species = MONTESINHO_CODES.get(code)
            if species is None:
                unknown.add(code)
            waves, vals = [], []
            with zf.open(name) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                for line in text:
                    parts = line.replace(",", " ").split()
                    if len(parts) < 2:
                        continue
                    wave = _as_float(parts[0])
                    value = _as_float(parts[1])
                    if wave is None or value is None:
                        continue  # the title and column-header lines
                    waves.append(wave)
                    vals.append(value)
            if not waves:
                continue
            bits = stem.split("_")
            yield build_row(
                entry, record, record_id=stem,
                wavelengths=waves, values=vals, species=species,
                extra={
                    "species": species,
                    "species_code": code,
                    "leaf": bits[1] if len(bits) > 1 else None,
                    "grid": bits[2] if len(bits) > 2 else None,
                    "plot": bits[3] if len(bits) > 3 else None,
                    "leaf_side": bits[4] if len(bits) > 4 else None,
                    "measurement_level": "leaf",
                    "archive_member": name,
                },
            )
        if unknown:
            gs.warning(_("Unrecognised species codes, left unnamed: {codes}")
                       .format(codes=", ".join(sorted(unknown))))


READERS = {"specveg": read_specveg, "montesinho": read_montesinho}


# ---------------------------------------------------------------------------
# Rows and storage
# ---------------------------------------------------------------------------

def _as_float(text):
    """Parse a float, returning None rather than raising."""
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def build_row(entry, record, record_id, wavelengths, values, species,
              extra, longitude=None, latitude=None):
    """Assemble one spectrum in the shared schema.

    The species is written into extra_metadata under the key "species"
    deliberately: that is the key the openspeclib loader reads to give a
    spectrum its material name. A library harvested with the species under
    any other key keeps its species on disk and loses it in the index, which
    is what happened to LOPEX93 and ANGERS, whose 1212 named spectra all
    reached the index carrying their dataset title instead.
    """
    meta = {k: v for k, v in (extra or {}).items() if v not in (None, "", "NA")}
    meta.setdefault("licence", entry.get("licence"))
    meta.setdefault("site", entry.get("site"))
    meta.setdefault("zenodo_doi", record.get("doi"))
    return {
        "source_database": SOURCE_DATABASE,
        "dataset_id": str(entry.get("record")),
        "dataset_title": entry.get("title"),
        "record_id": record_id,
        "organization": _creators(record),
        "source_url": f"https://doi.org/{record.get('doi')}"
                      if record.get("doi") else f"https://zenodo.org/records/"
                      f"{entry.get('record')}",
        "source_api_url": f"{ZENODO_API}/{entry.get('record')}",
        "longitude": longitude,
        "latitude": latitude,
        "measurement_type": "reflectance",
        "wavelength_unit": "nm",
        "n_bands": len(wavelengths),
        "wavelengths": wavelengths,
        "values": values,
        "extra_metadata": json.dumps(meta, default=str),
        "ingest_date": dt.datetime.now().isoformat(),
    }


def _creators(record):
    """A short creator string for the organization column."""
    names = [c.get("name", "") for c
             in record.get("metadata", {}).get("creators", [])]
    names = [n for n in names if n]
    if not names:
        return None
    return names[0] if len(names) == 1 else f"{names[0]} et al."


def load_manifest(root):
    """Read the shared manifest, or an empty one."""
    path = os.path.join(root, MANIFEST_NAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        gs.warning(_("Manifest at {p} is unreadable; starting a new one")
                   .format(p=path))
        return {}


def save_manifest(root, manifest):
    """Write the shared manifest atomically."""
    path = os.path.join(root, MANIFEST_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    Path(tmp).replace(path)


def write_parquet(root, dataset_id, rows):
    """Write one dataset's rows as a Parquet partition."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        gs.fatal(_("format=parquet requires the 'pyarrow' package "
                   "(pip install pyarrow). Use format=sqlite instead."))
    part = os.path.join(root, f"source_database={SOURCE_DATABASE}")
    os.makedirs(part, exist_ok=True)
    cols = {name: [r.get(name) for r in rows]
            for name, _ in _PARQUET_SCHEMA_FIELDS}
    # source_database is both the partition directory and a column, as the
    # other i.hyper.lib_* harvesters write it: openspeclib's loader requests
    # it explicitly in its COLUMNS list, so a partition without the column
    # fails to ingest with KeyError.
    table = pa.table({
        "source_database": pa.array(cols["source_database"], type=pa.string()),
        "dataset_id": pa.array(cols["dataset_id"], type=pa.string()),
        "dataset_title": pa.array(cols["dataset_title"], type=pa.string()),
        "record_id": pa.array(cols["record_id"], type=pa.string()),
        "organization": pa.array(cols["organization"], type=pa.string()),
        "source_url": pa.array(cols["source_url"], type=pa.string()),
        "source_api_url": pa.array(cols["source_api_url"], type=pa.string()),
        "longitude": pa.array(cols["longitude"], type=pa.float64()),
        "latitude": pa.array(cols["latitude"], type=pa.float64()),
        "measurement_type": pa.array(cols["measurement_type"],
                                     type=pa.string()),
        "wavelength_unit": pa.array(cols["wavelength_unit"], type=pa.string()),
        "n_bands": pa.array(cols["n_bands"], type=pa.int32()),
        "wavelengths": pa.array(cols["wavelengths"],
                                type=pa.list_(pa.float64())),
        "values": pa.array(cols["values"], type=pa.list_(pa.float64())),
        "extra_metadata": pa.array(cols["extra_metadata"], type=pa.string()),
        "ingest_date": pa.array(cols["ingest_date"], type=pa.string()),
    })
    out = os.path.join(part, f"dataset_{dataset_id}.parquet")
    pq.write_table(table, out, compression="snappy")
    return out


def write_sqlite(root, dataset_id, rows):
    """Write one dataset's rows into the fallback SQLite store."""
    import sqlite3
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, "hyperspeclib.sqlite")
    conn = sqlite3.connect(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spectra (
                source_database TEXT, dataset_id TEXT, dataset_title TEXT,
                record_id TEXT, organization TEXT, source_url TEXT,
                source_api_url TEXT, longitude REAL, latitude REAL,
                measurement_type TEXT, wavelength_unit TEXT, n_bands INTEGER,
                wavelengths TEXT, values_json TEXT, extra_metadata TEXT,
                ingest_date TEXT,
                PRIMARY KEY (source_database, dataset_id, record_id))""")
        conn.executemany(
            "INSERT OR REPLACE INTO spectra VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["source_database"], r["dataset_id"], r["dataset_title"],
              r["record_id"], r["organization"], r["source_url"],
              r["source_api_url"], r["longitude"], r["latitude"],
              r["measurement_type"], r["wavelength_unit"], r["n_bands"],
              json.dumps(r["wavelengths"]), json.dumps(r["values"]),
              r["extra_metadata"], r["ingest_date"]) for r in rows])
        conn.commit()
    finally:
        conn.close()
    return path


# ---------------------------------------------------------------------------

def list_registry():
    """Print the registry, with what each dataset actually contains."""
    for key, entry in REGISTRY.items():
        print(f"\n{key}")
        print(f"  Zenodo record : {entry['record']}  ({entry['licence']})")
        print(f"  Title         : {entry['title']}")
        print(f"  Site          : {entry['site']}")
        print(f"  Instrument    : {entry['instrument']}")
        print(f"  Range         : {entry['range_nm'][0]}-"
              f"{entry['range_nm'][1]} nm")
        print(f"  Species       : {', '.join(entry['species'])}")
        print(f"  Note          : {entry['note']}")


def main():
    options, flags = gs.parser()

    if flags["l"]:
        list_registry()
        return 0

    root = options["output"] or DEFAULT_ROOT
    cache_dir = options["cache_dir"] or os.path.join(root, "_cache",
                                                     SOURCE_DATABASE)
    keys = [k for k in (options["dataset"] or "").split(",") if k]
    records = [r for r in (options["record"] or "").split(",") if r]
    if records:
        known = {e["record"]: k for k, e in REGISTRY.items()}
        for rec in records:
            if rec not in known:
                gs.fatal(_("No reader knows record {rid}. Run with -l to see "
                           "the datasets this module can read.").format(
                               rid=rec))
            keys.append(known[rec])
    if not keys:
        keys = list(REGISTRY)
    for key in keys:
        if key not in REGISTRY:
            gs.fatal(_("Unknown dataset <{key}>; run with -l to list them")
                     .format(key=key))

    manifest = load_manifest(root)
    written = 0
    for key in keys:
        entry = REGISTRY[key]
        mkey = f"{SOURCE_DATABASE}:{entry['record']}"
        if mkey in manifest and not flags["f"]:
            gs.message(_("Dataset <{key}> is already in the manifest "
                         "({n} spectra); pass -f to re-harvest").format(
                             key=key, n=manifest[mkey].get("n_spectra", "?")))
            continue
        gs.message(_("Harvesting <{key}>: {title}").format(
            key=key, title=entry["title"]))
        record = api_record(entry["record"])
        if flags["n"]:
            gs.message(_("  would download: {files}").format(
                files=", ".join(entry["files"])))
            continue
        paths = {name: fetch_file(record, name, cache_dir)
                 for name in entry["files"]}
        reader = READERS[entry["reader"]]
        rows = list(reader(entry, record, paths))
        if not rows:
            gs.warning(_("Dataset <{key}> yielded no spectra").format(key=key))
            continue
        named = sum(1 for r in rows
                    if json.loads(r["extra_metadata"]).get("species"))
        if options["format"] == "sqlite":
            out = write_sqlite(root, entry["record"], rows)
        else:
            out = write_parquet(root, entry["record"], rows)
        gs.message(_("  {n} spectra ({named} with a species), wrote {out}")
                   .format(n=len(rows), named=named, out=out))
        manifest[mkey] = {
            "dataset_id": entry["record"],
            "dataset_title": entry["title"],
            "licence": entry["licence"],
            "doi": record.get("doi"),
            "n_spectra": len(rows),
            "n_with_species": named,
            "species": entry["species"],
            "harvested": dt.datetime.now().isoformat(),
        }
        written += len(rows)
    if written and not flags["n"]:
        save_manifest(root, manifest)
        gs.message(_("Wrote {n} spectra into {root}").format(n=written,
                                                             root=root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
