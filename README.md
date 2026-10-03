# cliiify

View IIIF manifests in the terminal.

## Install

```bash
git clone git@github.com:edwardanderson/cliiify.git
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

## Test

```bash
uv run pytest
```
