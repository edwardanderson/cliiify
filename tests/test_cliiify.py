import json

from cliiify.manifest import load_manifest
from cliiify.viewport import MAX_ZOOM, Viewport


# Manifest structure adapted from the IIIF Cookbook "Simplest Image" recipe
# (https://iiif.io/api/cookbook/recipe/0001-mvm-image/), simplified.
V3_MANIFEST = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "type": "Manifest",
    "label": {"en": ["Test Manifest"]},
    "items": [
        {
            "type": "Canvas",
            "items": [
                {
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "type": "Annotation",
                            "motivation": "painting",
                            "body": {
                                "id": "https://example.org/page1-full.png",
                                "type": "Image",
                            },
                        }
                    ],
                }
            ],
        }
    ],
}


def test_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(V3_MANIFEST))
    title, canvases = load_manifest(str(path))
    assert title == "Test Manifest"
    assert len(canvases) == 1
    assert canvases[0].image_url.endswith("page1-full.png")


def test_full_view_at_zoom_1():
    assert Viewport().rect(1200, 1800) == (0, 0, 1200, 1800)


def test_pan_ignored_at_zoom_1():
    v = Viewport()
    v.pan(5, 5)
    assert v.rect(100, 100) == (0, 0, 100, 100)


def test_zoom_limits():
    v = Viewport()
    for _ in range(100):
        v.zoom_in()
    assert v.zoom == MAX_ZOOM
    for _ in range(100):
        v.zoom_out()
    assert v.zoom == 1.0


def test_pan_clamps_to_edges():
    v = Viewport()
    v.zoom_by(2)
    v.pan(-100, -100)
    assert v.rect(100, 100) == (0, 0, 50, 50)
    v.pan(100, 100)
    assert v.rect(100, 100) == (50, 50, 50, 50)


def test_pan_step_scales_with_zoom():
    a, b = Viewport(), Viewport()
    a.zoom_by(2)
    b.zoom_by(4)
    a.pan(1, 0)
    b.pan(1, 0)
    assert round(a.cx - 0.5, 4) == 0.05
    assert round(b.cx - 0.5, 4) == 0.025


def test_reset():
    v = Viewport()
    v.zoom_by(4)
    v.pan(1, 1)
    v.reset()
    assert (v.zoom, v.cx, v.cy) == (1.0, 0.5, 0.5)


def test_v2_manifest():
    from cliiify.manifest import parse_manifest

    title, canvases = parse_manifest(
        {
            'label': 'T',
            'sequences': [
                {
                    'canvases': [
                        {
                            'label': 'fol. 1r',
                            'images': [
                                {'resource': {'@id': 'x', 'service': {'@id': 'http://h/img/1'}}}
                            ],
                        }
                    ]
                }
            ],
        }
    )
    assert title == 'T'
    assert canvases[0].label == 'fol. 1r'
    assert canvases[0].url_for(900) == 'http://h/img/1/full/900,/0/default.jpg'


def test_letterboxed_fit_centres_and_fills_on_zoom():
    v = Viewport()
    v.set_fit(2.0, 1.0)  # window twice as wide as the image
    assert v.rect(100, 100) == (0, 0, 100, 100)
    v.pan(5, 0)
    assert v.cx == 0.5
    v.zoom_by(4)  # window is now 50% x 25% of the image
    x, y, w, h = v.rect(100, 100)
    assert (x, w, h) == (25, 50, 25)
    assert abs(y - 37.5) <= 1


def test_v3_service_is_used_for_sized_urls():
    from cliiify.manifest import parse_manifest

    data = json.loads(json.dumps(V3_MANIFEST))
    body = data['items'][0]['items'][0]['items'][0]['body']
    body['service'] = [{'id': 'http://h/img/9', 'type': 'ImageService3'}]
    _, canvases = parse_manifest(data)
    assert canvases[0].url_for(800) == 'http://h/img/9/full/800,/0/default.jpg'
    assert canvases[0].image_url == 'https://example.org/page1-full.png'


def test_no_service_falls_back_to_body_id():
    from cliiify.manifest import parse_manifest

    _, canvases = parse_manifest(V3_MANIFEST)
    assert canvases[0].url_for(800) == 'https://example.org/page1-full.png'


def test_rect_within_a_region_image():
    v = Viewport()
    v.zoom_by(4)  # visible window: 25% of the image, centred
    # An image covering the middle half of the page, 200px wide.
    x, y, w, h = v.rect(200, 200, (0.25, 0.25, 0.75, 0.75))
    assert (w, h) == (100, 100)
    assert (x, y) == (50, 50)


def test_frac_rect_matches_rect():
    v = Viewport()
    v.zoom_by(2)
    v.pan(-100, 100)
    x0, y0, x1, y1 = v.frac_rect()
    assert (x0, y0, x1, y1) == (0.0, 0.5, 0.5, 1.0)
    assert v.rect(100, 100) == (0, 50, 50, 50)


def test_region_url_uses_native_pixels():
    from cliiify.manifest import Canvas

    canvas = Canvas('c', 'http://h/img', 'http://h/img/', 4000, 2000)
    url = canvas.region_url((0.25, 0.5, 0.75, 1.0), 800)
    assert url == 'http://h/img/1000,1000,2000,1000/800,/0/default.jpg'


def test_region_fetching_needs_service_and_size():
    from cliiify.manifest import Canvas

    assert not Canvas('c', 'u').can_fetch_regions
    assert not Canvas('c', 'u', 'http://h/img').can_fetch_regions
    assert Canvas('c', 'u', 'http://h/img', 10, 10).can_fetch_regions


def test_v2_native_size_is_read():
    from cliiify.manifest import parse_manifest

    _, canvases = parse_manifest(
        {
            'sequences': [
                {
                    'canvases': [
                        {
                            'images': [
                                {
                                    'resource': {
                                        '@id': 'x',
                                        'width': 4317,
                                        'height': 2855,
                                        'service': {'@id': 'http://h/img/1'},
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )
    assert (canvases[0].width, canvases[0].height) == (4317, 2855)
    assert canvases[0].can_fetch_regions
