## DESCRIPTION

*i.hyper.lib_zenodo* harvests curated spectral libraries published on
**Zenodo** into the same shared, source-tagged, partitioned local spectral
database used by *i.hyper.lib_ecosis*, *i.hyper.lib_gsti*,
*i.hyper.lib_relab* and *i.hyper.lib_usgs*. The default store is
`$HOME/grassdata/hyperspeclib`, written as Hive-partitioned Parquet under
`source_database=zenodo`, with a `_manifest.json` so a second run is
incremental.

### Why this module exists

The five libraries already harvested are global or North American. Between
them they hold almost no Mediterranean vegetation. A search of the local
store for the species of a Provence site returned **4** spectra of *Quercus
ilex*, **20** of *Quercus pubescens* and **10** of *Laurus nobilis*, and
nothing at all for *Pinus halepensis*, *Olea europaea*, *Cupressus*,
*Pistacia*, *Arbutus unedo*, *Cistus* or *Rosmarinus*.

That matters more than a gap usually does. A spectral match always returns a
nearest neighbour, so matching a Mediterranean canopy against a North
American library does not return *no answer*: it returns a confident wrong
one. The regional libraries that fill the gap are published as individual
Zenodo records rather than as a single database, which is what this module
is for.

### The registry

Zenodo has no common spectral schema, so each dataset is read by its own
reader and declared in a registry carrying its record id, licence, site,
instrument and the species it actually contains, verified against the
dataset's own metadata rather than its abstract. Adding a library means
adding a registry entry and a reader. Run with **-l** to print the registry.

| Key | Record | Licence | Level | Species |
|---|---|---|---|---|
| `mediterranean_woodlands` | 5176824 | CC-BY-4.0 | canopy and leaf | *Quercus suber*, *Cistus salviifolius*, *Ulex europaeus*, C3 grass mixture |
| `montesinho` | 10798148 | CC-BY-4.0 | leaf | *Quercus rotundifolia*, *Quercus pyrenaica*, *Arbutus unedo*, *Cistus ladanifer*, *Erica arborea*, *Castanea sativa*, *Fraxinus angustifolia*, *Crataegus monogyna*, *Alnus glutinosa*, *Frangula alnus*, *Cytisus multiflorus*, *Genista falcata*, *Acacia dealbata*, *Dactylis glomerata*, *Trifolium repens* |

Two points about what these contain. **974 of the 1216 observations** in
`mediterranean_woodlands` are *canopy* rather than leaf measurements, which
is the reason to prefer it: a drone crown is a canopy, and a laboratory leaf
spectrum is not comparable to one. And *Quercus rotundifolia* in
`montesinho` is the Iberian holm oak of the *Quercus ilex* complex, the
nearest reference this harvest can offer to a Provence holm oak.

### Where the species goes, and why it is said explicitly

Each spectrum carries its species in `extra_metadata` under the key
**`species`**. That is the key the `openspeclib` loader reads to give a
spectrum its material name, and writing it anywhere else loses the species
between the store and the index. This is not hypothetical: the LOPEX93 and
ANGERS records already in the store hold their species under `Latin Name`,
which the loader does not read, so all **1212** of those named spectra reach
the index carrying their dataset title instead and cannot be found by
species.

## NOTES

Downloads are cached in `_cache/zenodo` under the store root and reused on a
later run. Each download is checked against the size Zenodo reports, because
a truncated file is otherwise parsed into a silently incomplete library.

A dataset already recorded in the manifest is skipped; pass **-f** to
re-harvest it. Use **-n** to see what would be fetched without writing.

As harvested, both datasets give a species to every spectrum: 538 of 538 for
`montesinho` and 1216 of 1216 for `mediterranean_woodlands`. Six of the latter
need recovering, because the 2012-03-10 session is missing from the dataset's
metadata table although its spectra are in the data file. Their species comes
from the target `ID` instead, which is sound because species and measurement
level are constant across all 27 targets, and each such row says so in
`species_source` and is reported as a warning rather than passed off silently.

One value in that dataset is not a taxon: `c3mixture`, a mixed C3 herbaceous
sward, carried in the genus column. It is renamed to `C3 grass mixture` and
marked `is_taxon: false` on its 251 rows, so a mixture is not matched against
as though it named a plant.

`format=parquet` needs `pyarrow`; `format=sqlite` has no extra dependency.

These are **leaf and canopy reference** spectra of Iberian and Mediterranean
flora, not of Provence itself. They narrow the gap; they do not close it. A
match against them is still a match against another site's plants, and the
only thing that settles a species on the ground is identification in the
field.

## EXAMPLES

List the registry without downloading anything:

```sh
i.hyper.lib_zenodo -l
```

Harvest everything into the default shared store:

```sh
i.hyper.lib_zenodo
```

Harvest one dataset into a chosen store, as SQLite:

```sh
i.hyper.lib_zenodo dataset=montesinho output=$HOME/grassdata/hyperspeclib \
    format=sqlite
```

Check what a record would cost before fetching it:

```sh
i.hyper.lib_zenodo record=5176824 -n
```

## SEE ALSO

*[i.hyper.lib_ecosis](i.hyper.lib_ecosis.md)*,
*[i.hyper.lib_gsti](i.hyper.lib_gsti.md)*,
*[i.hyper.lib_relab](i.hyper.lib_relab.md)*,
*[i.hyper.lib_usgs](i.hyper.lib_usgs.md)*,
*[i.hyper.speclookup](i.hyper.speclookup.md)*,
*[i.hyper.spectroscopy](i.hyper.spectroscopy.md)*

## REFERENCES

- Cerasoli, S., Campagnolo, M., Faria, J., Nogueira, C., Caldeira, M.C.
  (2021). *Spectral library of vegetation from Mediterranean woodlands.*
  Zenodo. <https://doi.org/10.5281/zenodo.5176824> (CC-BY-4.0)
- Poças, I., et al. (2024). *Spectral Library of Plant Species from
  Montesinho Natural Park in Portugal.* Data 9(5), 65.
  <https://doi.org/10.3390/data9050065>; dataset
  <https://doi.org/10.5281/zenodo.10798148> (CC-BY-4.0)

## AUTHORS

Spectral Feature Extraction and Interpretation Engine
