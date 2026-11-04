# i.hyper.lib_zenodo

Harvest curated spectral libraries published on **Zenodo** into the shared
local spectral database used by the `i.hyper.*` family
(`$HOME/grassdata/hyperspeclib`, Hive-partitioned Parquet under
`source_database=zenodo`).

## Why

The five libraries already harvested (`ecosis`, `gsti`, `ossl`, `relab`,
`usgs_splib07`) are global or North American. A search of the local store for
the species of a Provence drone site returned 4 spectra of *Quercus ilex*, 20
of *Quercus pubescens*, 10 of *Laurus nobilis*, and nothing at all for *Pinus
halepensis*, *Olea europaea*, *Cupressus*, *Pistacia*, *Arbutus unedo*,
*Cistus* or *Rosmarinus*.

A spectral match always returns a nearest neighbour, so matching a
Mediterranean canopy against a North American library does not fail visibly:
it returns a confident wrong answer. The regional libraries that close the gap
are published as individual Zenodo records, which is what this module reads.

## Datasets

| Key | Record | Spectra | Level | Flora |
|---|---|---|---|---|
| `mediterranean_woodlands` | [5176824](https://doi.org/10.5281/zenodo.5176824) | 1 216 | 974 canopy, 242 leaf | *Quercus suber*, *Cistus salviifolius*, *Ulex europaeus*, C3 grass mixture |
| `montesinho` | [10798148](https://doi.org/10.5281/zenodo.10798148) | 538 | leaf | 15 species incl. *Quercus rotundifolia*, *Quercus pyrenaica*, *Arbutus unedo*, *Cistus ladanifer*, *Erica arborea*, *Dactylis glomerata* |

Both readers are verified against the published files: **1 754 spectra, every
one of them carrying a species.** `montesinho` is 2 151 bands over
350–2500 nm; `mediterranean_woodlands` is 1 748 bands over 350–2299 nm.

Both are CC-BY-4.0. `mediterranean_woodlands` is the more useful of the two
for drone work, because most of it is canopy rather than leaf.

## Usage

```sh
i.hyper.lib_zenodo -l                      # list the registry, download nothing
i.hyper.lib_zenodo                         # harvest everything
i.hyper.lib_zenodo dataset=montesinho      # one dataset
i.hyper.lib_zenodo record=5176824 -n       # dry run
i.hyper.lib_zenodo dataset=montesinho -f   # re-harvest
```

`format=parquet` (default) needs `pyarrow`; `format=sqlite` has no extra
dependency. Downloads are cached under `_cache/zenodo` in the store root and
size-checked against what Zenodo reports.

## How the harvest reaches a search index

The store is only the first hop. `openspeclib` ingests each
`source_database=` partition into its validated store, and `specserve`
builds the resident index from that:

```sh
PYTHONPATH=~/dev/openspeclib/src python3 -m openspeclib.cli ingest \
    --source hyperspeclib_zenodo --input ~/grassdata/hyperspeclib \
    --output ~/grassdata/openspeclib/records
PYTHONPATH=~/dev/openspeclib/src python3 -m openspeclib.cli combine \
    --input ~/grassdata/openspeclib/records --output ~/grassdata/openspeclib
python3 ~/dev/specserve/build_index.py \
    --library ~/grassdata/openspeclib --out ~/grassdata/specserve
python3 ~/dev/specserve/derive_matrices.py ~/grassdata/specserve
```

Two things that cost a failed run when this module was first written. The
partition must carry `source_database` **as a column** as well as in the
directory name, because the loader requests it explicitly and a partition
without it fails to ingest with `KeyError: 'source_database'`. And the
running server keeps its index memory-mapped, so it goes on serving the old
one until it is restarted against the rebuilt directory.

## Adding a library

Add an entry to `REGISTRY` with its record id, licence, species and file list,
and a reader function to `READERS`. Write the species into `extra_metadata`
under the key `species` — that is the key the `openspeclib` loader reads for a
spectrum's material name. The LOPEX93 and ANGERS records already in the store
put theirs under `Latin Name`, which the loader does not read, so all 1 212 of
those named spectra are indexed under their dataset title and cannot be found
by species.

## Caveats

These are Iberian and Mediterranean reference spectra, not Provence ones, and
mostly leaf level outside `mediterranean_woodlands`. They narrow the gap; they
do not close it. Nothing here substitutes for identification in the field.

## Licence

Unlicense (public domain). The harvested data keeps its own licence, recorded
per spectrum in `extra_metadata` and per dataset in `_manifest.json`.
