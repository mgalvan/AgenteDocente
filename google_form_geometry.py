"""Deterministic, proportionate regular polygon figures for Google Forms."""
import math
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont
from models_api_flat import RegularPolygonDiagram


def measurement_label(spec):
    """Keep algebra intact, including older quizzes that stored it as a unit."""
    if spec.measurement_latex:
        unit = r"\,\mathrm{" + spec.unit + "}" if spec.unit else ''
        return spec.measurement_latex + unit, True
    if spec.unit and not re.fullmatch(r'(?:mm|cm|dm|m|dam|hm|km|in|ft|yd|mi|um|\u00b5m|\u03bcm|nm)', spec.unit):
        # Legacy schema used length as coefficient and unit as algebraic factor.
        return f'{spec.length:g}' + r'\left(' + spec.unit + r'\right)', True
    return f'{spec.length:g} {spec.unit}'.strip(), False


def polygon_image(raw):
    spec = RegularPolygonDiagram.model_validate(raw)
    canvas = Image.new('RGB', (1200, 900), 'white')
    draw = ImageDraw.Draw(canvas)
    fonts = [Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    font = next((ImageFont.truetype(str(p), 36) for p in fonts if p.exists()), ImageFont.load_default(size=36))
    def label_at(position, anchor):
        label, is_formula = measurement_label(spec)
        if not is_formula:
            draw.text(position, label, fill='#1d2939', font=font, anchor=anchor)
            return
        from visual_assets import formula
        asset = formula(label)
        with Image.open(asset.path) as source:
            picture = source.convert('RGBA')
        picture.thumbnail((430, 100), Image.Resampling.LANCZOS)
        x, y = position
        if anchor == 'mt':
            x -= picture.width // 2
        else:
            y -= picture.height // 2
        canvas.paste(picture, (int(x), int(y)), picture)

    cx, cy, radius = 600, 405, 300
    # The first edge is horizontal, with its midpoint directly below the centre.
    angles = [math.pi / 2 - math.pi / spec.sides + i * 2 * math.pi / spec.sides for i in range(spec.sides)]
    vertices = [(cx + radius * math.cos(a), cy + radius * math.sin(a)) for a in angles]
    draw.line(vertices + [vertices[0]], fill='#1d2939', width=5)
    midpoint = ((vertices[0][0] + vertices[1][0]) / 2, (vertices[0][1] + vertices[1][1]) / 2)
    if spec.show_apothem or spec.measure == 'apothem':
        for start in range(0, int(midpoint[1] - cy), 20):
            draw.line([(cx, cy + start), (cx, min(cy + start + 11, midpoint[1]))], fill='#087f78', width=4)
        x, y = midpoint
        draw.line([(x + 18, y), (x + 18, y - 18), (x, y - 18)], fill='#087f78', width=3)
        if spec.measure == 'apothem':
            label_at((cx + 25, (cy + y) / 2), 'lm')
        else:
            draw.text((cx + 25, (cy + y) / 2), 'a', fill='#087f78', font=font, anchor='lm')
        draw.ellipse((cx-5, cy-5, cx+5, cy+5), fill='#087f78')
    if spec.measure == 'side':
        draw.line(vertices[:2], fill='#c45821', width=7)
        label_at((midpoint[0], midpoint[1]+35), 'mt')
    return canvas
