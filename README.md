# cliiify

View IIIF v2 and v3 manifests in the terminal.

Images only: it shows one painted image per canvas. Audio/video, collections,
annotations, ranges and metadata are not displayed.

## Install

```bash
git clone https://github.com/edwardanderson/cliiify.git
uv tool install --editable cliiify/
```

## Quickstart

```bash
cliiify https://iiif.bodleian.ox.ac.uk/iiif/manifest/fd4b8844-8100-4794-a0bb-fb32acd6bf36.json
```

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

## Dependencies

- [chafa.py](https://github.com/GuardKenzie/chafa.py)

## Test

```bash
uv run pytest
```
