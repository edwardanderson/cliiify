import argparse
import sys

from .app import run
from .manifest import load_manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog='cliiify', description='View IIIF manifests in the terminal')
    parser.add_argument('manifest', help='path or URL of a IIIF v2 or v3 manifest')
    args = parser.parse_args()
    try:
        title, canvases = load_manifest(args.manifest)
    except Exception as exc:
        sys.exit(f'cliiify: cannot load manifest: {exc}')

    if not canvases:
        sys.exit('cliiify: no image canvases found in manifest')

    run(title, canvases)


if __name__ == '__main__':
    main()
