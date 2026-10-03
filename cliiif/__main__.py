import argparse
import sys

from .app import CliiifApp
from .manifest import load_manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="cliiif", description="IIIF manifest viewer")
    parser.add_argument("manifest", help="path or URL of a IIIF v2 or v3 manifest")
    args = parser.parse_args()
    try:
        title, canvases = load_manifest(args.manifest)
    except Exception as exc:
        sys.exit(f"cliiif: cannot load manifest: {exc}")
    if not canvases:
        sys.exit("cliiif: no image canvases found in manifest")
    CliiifApp(title, canvases).run()


if __name__ == "__main__":
    main()
