# Map geometry (one-time prep)

The `/congress` geographic map (`frontend/components/UsMap.tsx`) renders **bundled**
TopoJSON — no map tiles, no third-party requests at runtime. It expects two files:

```
frontend/public/geo/districts-119.topo.json   # 119th-Congress districts, object name: "districts"
frontend/public/geo/states-119.topo.json      # states,                    object name: "states"
```

Until these exist, the map **gracefully falls back** to the self-contained seat
chart, so the page always works. Do this once (needs Node — `npx` runs mapshaper
without installing it), commit the two JSON files, and the map upgrades itself.

## 1. Get the public-domain Census shapefiles

Cartographic Boundary files (simplified, public domain) from the Census GENZ dir.
Grab the **current 119th-Congress** district file and the states file — adjust the
year in the filename if a newer vintage exists:

- Districts: `https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_cd119_500k.zip`
- States:    `https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip`

Unzip both (each is a `.shp` + siblings).

## 2. Convert to simplified TopoJSON

Run from the repo root (so the output paths land correctly). The component reads
the district key from the `GEOID` field (state FIPS + district, e.g. `5307` = WA-7)
and the state key from `STATEFP`/`GEOID` — both are standard Census fields, so no
field renaming is needed.

```bash
mkdir -p frontend/public/geo

# Districts  (~435 polygons -> well under 1 MB after simplify)
npx mapshaper cb_2024_us_cd119_500k.shp \
  -rename-layers districts \
  -simplify 8% keep-shapes \
  -o format=topojson frontend/public/geo/districts-119.topo.json

# States
npx mapshaper cb_2024_us_state_500k.shp \
  -rename-layers states \
  -simplify 8% keep-shapes \
  -o format=topojson frontend/public/geo/states-119.topo.json
```

`-rename-layers` makes the TopoJSON object name predictable (`districts` / `states`),
which is what `UsMap.tsx` looks up. If the files come out larger than ~1 MB, lower
the simplify percentage (e.g. `-simplify 5%`).

## 3. Verify

- Commit the two `*.topo.json` files, deploy, open `/congress`.
- The House map should color every district by party; hover shows the rep, click
  opens their profile; the Senate toggle colors states (split states in violet).
- A ZIP lookup rings your district (House) / state (Senate).
- **DevTools → Network:** confirm the only geo requests are same-origin
  `/geo/*.topo.json` — no tile/CDN hosts.

If the map draws but every district is grey, the browser console logs
`UsMap: districts drew but none matched /api/map keys` — that means the `GEOID`
field wasn't preserved; re-run without any `-filter-fields`/`drop-table` step so
`GEOID`/`STATEFP` stay on the features.
