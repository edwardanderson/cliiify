from pathlib import Path

from cliiif.manifest import load_manifest
from cliiif.viewport import MAX_ZOOM, Viewport

SAMPLE = Path(__file__).parent.parent / "manifest" / "0001-mvm-image.json"


def test_manifest():
    title, canvases = load_manifest(str(SAMPLE))
    assert title.startswith("Simplest Image")
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
    from cliiif.manifest import parse_manifest

    title, canvases = parse_manifest(
        {
            "label": "T",
            "sequences": [
                {
                    "canvases": [
                        {
                            "label": "fol. 1r",
                            "images": [
                                {"resource": {"@id": "x", "service": {"@id": "http://h/img/1"}}}
                            ],
                        }
                    ]
                }
            ],
        }
    )
    assert title == "T"
    assert canvases[0].label == "fol. 1r"
    assert canvases[0].image_url == "http://h/img/1/full/2000,/0/default.jpg"
