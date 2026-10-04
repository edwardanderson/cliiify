# cliiify

View IIIF manifests and images in the terminal.

<video autoplay muted loop src="demo.mp4"/>

Image: Rembrandt, H. van Rijn. (1642). _The Night Watch_ [Oil on canvas]. Rijksmuseum Amsterdam, Netherlands. <https://www.rijksmuseum.nl/nl/collectie/object/De-Nachtwacht>.

## Install

```bash
git clone https://github.com/edwardanderson/cliiify.git
uv tool install --editable cliiify/
```

## Quickstart

View a IIIF presentation manifest:

```bash
cliiify manifest https://iiif.bodleian.ox.ac.uk/iiif/manifest/fd4b8844-8100-4794-a0bb-fb32acd6bf36.json
```

View a single IIIF image:

```bash
cliiify image https://iiif.micr.io/PJEZO
```

> [!NOTE]
> Only pass the image identifier (the IIIF Image API base URI), and not an image request that includes region, size, rotation and quality parameters.

### Controls

| Control    | Key               |
|-           |-                  |
| Pan        | `↑` `←` `→` `↓`   |
| Fast pan   | `Shift +` pan     |
| Zoom in    | `+` or `=`        |
| Zoom out   | `-`               |
| Reset zoom | `0`               |
| Next       | `n` or `PgDn`     |
| Previous   | `p` or `PgUp`     |
| Quit       | `q` or `Ctrl + c` |

When an image has a IIIF Image API service, zooming in re-requests the visible region at higher resolution once the view settles (the status bar shows `refining…`, then `detail`). The request includes some extra surrounding image, so panning stays sharp while the next region is fetched.

## Test

```bash
uv run pytest
```
