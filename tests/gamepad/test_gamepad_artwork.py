from pathlib import Path
import sys

import pytest

cairo = pytest.importorskip("cairo")
gi = pytest.importorskip("gi")
try:
    gi.require_version("Rsvg", "2.0")
except ValueError:
    pytest.skip(
        "Rsvg introspection is required for SVG rendering", allow_module_level=True
    )

from waydroid_helper.gamepad_artwork import ArtworkPalette, ControllerArtwork

ASSETS = Path(__file__).resolve().parents[2] / "data" / "gamepads"


@pytest.mark.parametrize(
    "path", sorted(ASSETS.glob("*.svg")), ids=lambda path: path.stem
)
def test_original_steam_artwork_renders_neutral_and_active_inputs(path):
    artwork = ControllerArtwork(path.read_bytes())
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 500, 350)
    context = cairo.Context(surface)
    artwork.render(artwork.frame([False] * 26, [0] * 6, []), context, 500, 350)
    neutral = bytes(surface.get_data())
    assert any(neutral)
    context.set_operator(cairo.OPERATOR_CLEAR)
    context.paint()
    context.set_operator(cairo.OPERATOR_OVER)
    artwork.render(
        artwork.frame(
            [True] * 26,
            [32767, -32768, -32768, 32767, 32767, 32767],
            [(0, 0, 0.25, 0.75, 1)],
        ),
        context,
        500,
        350,
    )
    assert bytes(surface.get_data()) != neutral


@pytest.mark.parametrize(
    "path", sorted(ASSETS.glob("*.svg")), ids=lambda path: path.stem
)
def test_light_and_dark_palettes_preserve_original_geometry(path):
    artwork = ControllerArtwork(path.read_bytes())
    palettes = (
        ArtworkPalette("black", "#3584e4", (1, 1, 1), (0, 0, 0)),
        ArtworkPalette("white", "#3584e4", (0.11, 0.11, 0.12), (1, 1, 1)),
    )
    rendered = []
    for palette in palettes:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 500, 350)
        artwork.render(
            artwork.frame([False] * 26, [0] * 6, [], palette),
            cairo.Context(surface),
            500,
            350,
        )
        rendered.append(bytes(surface.get_data()))
    assert rendered[0] != rendered[1]
    # Changing appearance may recolor strokes and glyphs, but must not alter
    # Steam's paths, stroke coverage or proportions in either color scheme.
    alpha_offset = 3 if sys.byteorder == "little" else 0
    assert rendered[0][alpha_offset::4] == rendered[1][alpha_offset::4]


def test_high_contrast_uses_theme_ink_instead_of_pastel_glyphs():
    palette = ArtworkPalette(
        "black", "#3584e4", (1, 1, 1), (0, 0, 0), high_contrast=True
    )
    assert palette.source_color("#3CCAD0") == "currentColor"
    assert palette.source_color("#D6B4D7") == "currentColor"
    assert palette.source_color("none") == "none"


def test_stick_motion_and_button_highlights_reuse_render_nodes(monkeypatch):
    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Adw, Gdk, Gtk
    from waydroid_helper.gamepad_diagram import GamepadDiagram

    if not Gtk.init_check() or not Gdk.Display.get_default():
        pytest.skip("GTK display unavailable")
    Adw.init()
    diagram = GamepadDiagram()
    diagram.artwork = ControllerArtwork((ASSETS / "ps5.svg").read_bytes())
    diagram.allocate(473, 260, -1, None)
    palette = ArtworkPalette("white", "#3584e4", (0.1, 0.1, 0.1), (1, 1, 1))
    monkeypatch.setattr(diagram, "_palette", lambda: palette)
    prepare = diagram.artwork.prepare_nodes
    builds = []

    def prepare_once(*args):
        builds.append(args)
        return prepare(*args)

    monkeypatch.setattr(diagram.artwork, "prepare_nodes", prepare_once)

    def pixels():
        shot = Gtk.Snapshot()
        diagram.do_snapshot(shot)
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, diagram.get_width(), diagram.get_height()
        )
        shot.to_node().draw(cairo.Context(surface))
        return bytes(surface.get_data())

    rest = pixels()
    buttons = [False] * 26
    axes = [-28000, 13000, 23000, 17000, 0, 0]
    diagram.set_state(buttons, axes)
    moved = pixels()
    assert moved != rest
    buttons[0] = True
    diagram.set_state(buttons, axes)
    assert pixels() != moved
    diagram.set_state([False] * 26, [0] * 6)
    assert pixels() == rest
    assert len(builds) == 1

    palette = ArtworkPalette("black", "#ff8800", (1, 1, 1), (0, 0, 0))
    assert pixels() != rest
    diagram.allocate(360, 200, -1, None)
    pixels()
    assert len(builds) == 3
