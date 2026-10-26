"""Render quiz prose and LaTeX into a self-contained PNG using the existing math renderer."""
import io
import re
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFont
from image_renderers import _DELIMITED


def rich_block(text):
    segments = []
    cursor = 0
    for match in _DELIMITED.finditer(text):
        if match.start() > cursor:
            segments.append({'type': 'text', 'content': text[cursor:match.start()]})
        raw = match.group()
        n = 2 if raw.startswith(('$$', r'\[', r'\(')) else 1
        segments.append({'type': 'formula', 'latex': raw[n:-n], 'alt_text': '', 'display': 'inline'})
        cursor = match.end()
    if cursor < len(text):
        segments.append({'type': 'text', 'content': text[cursor:]})
    return {'block_type': 'text', 'segments': segments or [{'type': 'text', 'content': text}]}


def option_text(text):
    # Preserve simple numeric answers as text, even when wrapped in LaTeX.
    segments = rich_block(text)['segments']
    numeric = re.compile(r'[+-]?(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)%?')
    if all(segment['type'] == 'text' or numeric.fullmatch(segment['latex'].strip())
           for segment in segments):
        return ''.join(segment.get('content', segment.get('latex', '')).strip()
                       if segment['type'] == 'formula' else segment['content']
                       for segment in segments)
    return None


def question_image(question):
    diagrams = question.get('diagrams', [])
    if not diagrams:
        return text_image(question['title'])
    from google_form_geometry import polygon_image
    title = text_image(question['title'], force=True)
    with Image.open(io.BytesIO(title)) as source:
        heading = source.convert('RGB')
    figure = polygon_image(diagrams[0])
    canvas = Image.new('RGB', (1480, heading.height + figure.height), 'white')
    canvas.paste(heading, (0, 0))
    canvas.paste(figure, ((1480 - figure.width) // 2, heading.height))
    output = io.BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    return output.getvalue()


def text_image(text, width=1480, margin=48, tight=False, force=False):
    texts = [text]
    if not force and not any(_DELIMITED.search(text) for text in texts):
        return None
    from visual_assets import formula
    gap = 12
    font_paths = [Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    font = next((ImageFont.truetype(str(p), 44) for p in font_paths if p.exists()), ImageFont.load_default(size=44))
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    rows = []
    for text in texts:
        units = []
        for segment in rich_block(text)['segments']:
            if segment['type'] == 'formula':
                asset = formula(segment['latex'])
                with Image.open(asset.path) as original:
                    picture = original.convert('RGBA').copy()
                if picture.width > width - 2 * margin:
                    picture.thumbnail((width - 2 * margin, picture.height), Image.Resampling.LANCZOS)
                units.append(picture)
            else:
                units.extend(re.findall(r'\n|[^\S\n]+|[^\s]+', segment['content']))
        line, used, height = [], 0, 60
        def flush():
            nonlocal line, used, height
            if line:
                rows.append((line, height))
            line, used, height = [], 0, 60
        for unit in units:
            if isinstance(unit, str) and unit == '\n':
                flush(); continue
            unit_width = unit.width if isinstance(unit, Image.Image) else int(measure.textlength(unit, font=font))
            if isinstance(unit, str) and unit_width > width - 2 * margin:
                raise ValueError('Testo del quiz troppo lungo senza spazi: suddividere la parola o la formula.')
            if used + unit_width > width - 2 * margin:
                flush()
            if not line and isinstance(unit, str) and unit.isspace():
                continue
            line.append((unit, unit_width))
            used += unit_width
            if isinstance(unit, Image.Image): height = max(height, unit.height + gap)
        flush()
        rows.append(([], 28))
    height = 2 * margin + sum(h for _, h in rows)
    if height > 16000:
        raise ValueError('Immagine della domanda troppo alta: ridurre il testo o le opzioni.')
    canvas = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(canvas)
    y = margin
    for line, row_height in rows:
        x = margin
        for unit, unit_width in line:
            if isinstance(unit, Image.Image):
                canvas.paste(unit, (x, y + (row_height - unit.height) // 2), unit)
            else:
                draw.text((x, y + row_height // 2), unit, font=font, fill='#1d2939', anchor='lm')
            x += unit_width
        y += row_height
    if tight:
        bounds = ImageChops.difference(canvas, Image.new('RGB', canvas.size, 'white')).getbbox()
        if bounds:
            left, top, right, bottom = bounds
            padding = 16
            canvas = canvas.crop((max(0, left - padding), max(0, top - padding),
                                  min(canvas.width, right + padding), min(canvas.height, bottom + padding)))
    output = io.BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    return output.getvalue()
