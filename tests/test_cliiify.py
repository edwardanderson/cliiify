import json

from cliiify.image import load_image
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


def test_image_service_base_url():
    title, canvases = load_image('https://example.org/image/abc')
    assert title == 'abc'
    assert canvases[0].service == 'https://example.org/image/abc'


def test_image_info_json_url_tolerated():
    _, canvases = load_image('https://example.org/image/abc/info.json')
    assert canvases[0].service == 'https://example.org/image/abc'


def test_image_rejects_request_parameters():
    import pytest

    with pytest.raises(ValueError, match='https://example.org/image/abc$'):
        load_image('https://example.org/image/abc/full/max/0/default.jpg')


def test_base_size_fits_terminal_without_upscaling():
    from cliiify.image import base_size

    assert base_size((2436, 3582), (120, 39)) == round(39 * 8 * 2436 / 3582)
    assert base_size((300, 300), (200, 100)) == 300


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


def test_detail_request_skipped_when_base_is_sharp_enough():
    from cliiify.image import detail_request

    assert detail_request('http://h/i', (0, 0, 2000, 3000), (100, 40), 2000) is None


def test_detail_request_asks_for_visible_region():
    from cliiify.image import detail_request

    key, url = detail_request('http://h/i', (100, 200, 400, 600), (100, 40), 60)
    assert url == 'http://h/i/100,200,400,600/213,/0/default.jpg'
    assert key == (100, 200, 400, 600, 213)


def test_detail_request_size_limited_by_terminal():
    from cliiify.image import detail_request

    _, url = detail_request('http://h/i', (0, 0, 5000, 5000), (50, 20), 10)
    assert url.endswith('/160,/0/default.jpg')


def test_v3_manifest_service():
    from cliiify.manifest import parse_manifest

    import copy

    m = copy.deepcopy(V3_MANIFEST)
    body = m['items'][0]['items'][0]['items'][0]['body']
    body['service'] = [{'id': 'https://example.org/img/1/', 'type': 'ImageService3'}]
    assert parse_manifest(m)[1][0].service == 'https://example.org/img/1'


def test_tile_plan_pads_and_clamps_to_image():
    from cliiify.image import tile_plan

    tile, size, url = tile_plan('http://h/i', (10000, 10000), (1000, 1000, 200, 100), 100)
    assert tile == (850, 925, 500, 250)
    assert size == 375  # 1.5x the density needed
    assert url == 'http://h/i/850,925,500,250/375,/0/default.jpg'


def test_tile_plan_never_exceeds_source_pixels():
    from cliiify.image import tile_plan

    tile, size, _ = tile_plan('http://h/i', (1000, 1000), (100, 100, 200, 100), 200)
    assert size == tile[2]


def test_covers_with_margin():
    from cliiify.image import covers

    tile = (0, 0, 100, 100)
    assert covers(tile, (20, 20, 60, 60))
    assert not covers(tile, (20, 20, 60, 60), 0.5)
    assert not covers(tile, (50, 50, 60, 60))


def test_tile_usable_needs_cover_and_sharpness():
    from cliiify.image import tile_usable

    tile = (0, 0, 400, 400)
    assert tile_usable(tile, 800, (100, 100, 200, 200), 400)
    assert not tile_usable(tile, 200, (100, 100, 200, 200), 400)  # too soft
    assert not tile_usable(tile, 800, (300, 300, 200, 200), 400)  # not covered


def test_covers_margin_clamped_to_image():
    from cliiify.image import covers

    # Tile spans the whole image width, so no margin can push past its edge.
    assert covers((0, 0, 100, 100), (0, 0, 100, 50), 0.5, (100, 100))
    assert not covers((0, 0, 100, 100), (0, 0, 100, 50), 0.5)


def test_tile_fresh_requires_density_and_edge_room():
    from cliiify.image import tile_fresh

    full = (10000, 10000)
    tile = (0, 0, 2000, 2000)
    rect = (800, 800, 400, 400)
    assert tile_fresh(tile, 1000, rect, 200, full)  # 0.5 px/px, wants 0.5
    assert not tile_fresh(tile, 900, rect, 200, full)  # a bit soft: refetch early
    assert not tile_fresh(tile, 1000, (1500, 800, 400, 400), 200, full)  # near edge


def test_zoom_limit_is_one_source_pixel_per_terminal_pixel():
    v = Viewport()
    v.set_fit(1.0, 1.0)
    v.limit_to(14645, 200, 2)
    assert round(v.max_zoom, 1) == 36.6
    for _ in range(100):
        v.zoom_in()
    assert v.zoom == v.max_zoom


def test_zoom_limit_floor_and_shrinking_terminal():
    v = Viewport()
    v.set_fit(1.0, 1.0)
    v.limit_to(100, 200, 2)  # image smaller than the terminal
    assert v.max_zoom == 1.0
    v.limit_to(10000, 100, 2)
    v.zoom_by(1000)
    v.limit_to(10000, 400, 2)  # terminal grows: limit drops, zoom follows
    assert v.zoom == v.max_zoom == 12.5
