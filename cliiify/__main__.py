import argparse
import sys

from .app import run
from .image import load_image
from .manifest import load_manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='cliiify', description='View IIIF manifests and images in the terminal'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    manifest_parser = subparsers.add_parser(
        'manifest', help='view a IIIF presentation manifest (v2 or v3)'
    )
    manifest_parser.add_argument('source', help='path or URL of a IIIF manifest')

    image_parser = subparsers.add_parser('image', help='view a single IIIF image')
    image_parser.add_argument(
        'source',
        help='path or URL of a IIIF image (service base URL, info.json, image request URL, or local file)',
    )

    args = parser.parse_args()
    load = load_manifest if args.command == 'manifest' else load_image
    try:
        title, canvases = load(args.source)
    except Exception as exc:
        sys.exit(f'cliiify: cannot load {args.command}: {exc}')

    if not canvases:
        sys.exit(f'cliiify: no images found in {args.command}')

    run(title, canvases)


if __name__ == '__main__':
    main()
