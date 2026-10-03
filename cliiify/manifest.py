import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Canvas:
    label: str
    image_url: str
    # Base URL of a IIIF Image API service for the image, if the manifest has one.
    service: str | None = None
    # Pixel size of the full image, needed to request regions.
    width: int | None = None
    height: int | None = None

    @property
    def can_fetch_regions(self) -> bool:
        return bool(self.service and self.width and self.height)

    def region_url(
        self, region: tuple[float, float, float, float], width: int
    ) -> str:
        """URL of a region (fractions of the full image) scaled to the given width."""
        assert self.service and self.width and self.height
        x0, y0, x1, y1 = region
        x, y = round(x0 * self.width), round(y0 * self.height)
        w, h = round((x1 - x0) * self.width), round((y1 - y0) * self.height)
        return f"{self.service.rstrip('/')}/{x},{y},{w},{h}/{width},/0/default.jpg"

    def url_for(self, width: int) -> str:
        """URL of the image scaled to the given width, when a service allows it."""
        if self.service:
            return f"{self.service.rstrip('/')}/full/{width},/0/default.jpg"
        return self.image_url


def _image_service(body: dict) -> str | None:
    services = body.get('service') or body.get('@service') or []
    if isinstance(services, dict):
        services = [services]
    for service in services:
        if not isinstance(service, dict):
            continue
        kind = str(service.get('type') or service.get('@type') or '')
        url = service.get('id') or service.get('@id')
        if url and (not kind or kind.startswith('ImageService')):
            return url
    return None


def _label(value, default: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _label(value[0], default)
    if isinstance(value, dict) and '@value' in value:
        return str(value['@value'])
    if isinstance(value, dict):
        for texts in value.values():
            if texts:
                return str(texts[0])
    return default


def _parse_v2(data: dict) -> tuple[str, list[Canvas]]:
    canvases = []
    for sequence in data.get('sequences', [])[:1]:
        for i, canvas in enumerate(sequence.get('canvases', []), 1):
            label = _label(canvas.get('label'), f'Canvas {i}')
            for anno in canvas.get('images', []):
                res = anno.get('resource', {})
                service = _image_service(res)
                url = res.get('@id') or service
                if not url:
                    continue
                canvases.append(
                    Canvas(label, url, service, res.get('width'), res.get('height'))
                )
                break
    return _label(data.get('label'), 'Untitled'), canvases


def parse_manifest(data: dict) -> tuple[str, list[Canvas]]:
    if 'sequences' in data:
        return _parse_v2(data)
    title = _label(data.get('label'), 'Untitled')
    canvases = []
    for i, canvas in enumerate(data.get('items', []), 1):
        label = _label(canvas.get('label'), f'Canvas {i}')
        for page in canvas.get('items', []):
            for anno in page.get('items', []):
                body = anno.get('body')
                if (
                    anno.get('motivation') == 'painting'
                    and isinstance(body, dict)
                    and body.get('type') == 'Image'
                ):
                    canvases.append(
                        Canvas(
                            label,
                            body['id'],
                            _image_service(body),
                            body.get('width'),
                            body.get('height'),
                        )
                    )
                    break
            else:
                continue
            break
    return title, canvases


def load_manifest(source: str) -> tuple[str, list[Canvas]]:
    if source.startswith(('http://', 'https://')):
        with urllib.request.urlopen(source, timeout=30) as resp:
            data = json.load(resp)
    else:
        data = json.loads(Path(source).read_text())
    return parse_manifest(data)
