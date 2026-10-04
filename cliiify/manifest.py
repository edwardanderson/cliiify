import json
from dataclasses import dataclass
from pathlib import Path

from .net import urlopen


@dataclass
class Canvas:
    label: str
    image_url: str
    # IIIF Image API service base URL, when known; enables region requests.
    service: str | None = None


# Width requested from IIIF Image API services (level 1 supports 'w,' sizes).
IMAGE_WIDTH = 2000


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


def _service_v3(body: dict) -> str | None:
    services = body.get('service') or []
    if isinstance(services, dict):
        services = [services]
    for service in services:
        if isinstance(service, dict):
            sid = service.get('id') or service.get('@id')
            if isinstance(sid, str):
                return sid.rstrip('/')
    return None


def _parse_v2(data: dict) -> tuple[str, list[Canvas]]:
    canvases = []
    for sequence in data.get('sequences', [])[:1]:
        for i, canvas in enumerate(sequence.get('canvases', []), 1):
            label = _label(canvas.get('label'), f'Canvas {i}')
            for anno in canvas.get('images', []):
                res = anno.get('resource', {})
                service = res.get('service')
                if isinstance(service, list) and service:
                    service = service[0]
                base = None
                if isinstance(service, dict) and '@id' in service:
                    base = service['@id'].rstrip('/')
                    url = f'{base}/full/{IMAGE_WIDTH},/0/default.jpg'
                elif '@id' in res:
                    url = res['@id']
                else:
                    continue
                canvases.append(Canvas(label, url, base))
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
                    canvases.append(Canvas(label, body['id'], _service_v3(body)))
                    break
            else:
                continue
            break
    return title, canvases


def load_manifest(source: str) -> tuple[str, list[Canvas]]:
    if source.startswith(('http://', 'https://')):
        with urlopen(source, timeout=30) as resp:
            data = json.load(resp)
    else:
        data = json.loads(Path(source).read_text())
    return parse_manifest(data)
