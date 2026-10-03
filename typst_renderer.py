"""Alternative PDF backend: Typst layout, Lilaq plots, MathJax SVG math."""
import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from visual_assets import graph_curves, evaluate_expression, resolved_curves
from models_api_flat import Area, Rectangles, Polygon
from image_renderers import _DELIMITED

ROOT = Path(__file__).resolve().parent

def quote(value):
    return json.dumps(str(value), ensure_ascii=False)

def nums(values):
    values=list(values)
    if not all(np.isfinite(v) for v in values):
        raise ValueError('Coordinate grafiche non finite')
    return '(' + ','.join(repr(float(v)) for v in values) + ',)'


def finite_runs(x, y):
    valid=np.isfinite(x) & np.isfinite(y)
    boundaries=np.flatnonzero(np.diff(np.r_[False, valid, False]))
    return [(x[a:b], y[a:b]) for a,b in zip(boundaries[::2],boundaries[1::2]) if b-a>=2]


def plot(spec):
    vp=spec['viewport']; limits=[float(vp[k]) for k in ('x_min','x_max','y_min','y_max')]
    if not np.isfinite(limits).all() or limits[0]>=limits[1] or limits[2]>=limits[3]:
        raise ValueError('Limiti grafico non validi')
    children=[]; kind=spec.get('kind',spec.get('renderer'))
    if kind=='function_2d':
        for area in spec.get('areas',[]):
            a=Area.model_validate(area);x=np.linspace(a.x_start,a.x_end,250);y=evaluate_expression(a.expression,x)
            if not np.isfinite(y).all():raise ValueError('Area non finita')
            children.append(f'lq.fill-between({nums(x)}, {nums(y)}, y2: {nums(np.full(x.shape,a.baseline))}, fill: rgb("#c6e4df"))')
        for raw in spec.get('rectangles',[]):
            r=Rectangles.model_validate(raw);edges=np.linspace(r.x_start,r.x_end,r.count+1)
            width=(r.x_end-r.x_start)/r.count
            y=evaluate_expression(r.expression,edges[:-1]+width*{'left':0,'right':1,'midpoint':.5}[r.sample])
            if not np.isfinite(y).all():raise ValueError('Rettangoli non finiti')
            for left,right,height in zip(edges[:-1],edges[1:],y):
                children.append(f'lq.fill-between({nums([left,right])}, {nums([height,height])}, y2: {nums([r.baseline,r.baseline])}, fill: rgb("#f3d9ac"), stroke: .4pt + rgb("#a87926"))')
        curves,markers=resolved_curves(spec,limits)
        for i,(label,x,y) in enumerate(curves):
            labels=spec.get('labels',[]) if not spec.get('points') else []
            if i<len(labels):label=labels[i]
            color=('#087f78','#b45b20','#6950a1','#246db3')[i%4]
            for j,(xs,ys) in enumerate(finite_runs(x,y)):
                legend=f', label: text({quote(label)})' if j==0 else ''
                children.append(f'lq.plot({nums(xs)}, {nums(ys)}, stroke: 1pt + rgb({quote(color)}){legend})')
        for x,y,state in markers:
            fill='white' if state=='open' else 'black'
            children.append(f'lq.place({x}, {y}, circle(radius: 4pt, fill: {fill}, stroke: 1.1pt + black), z-index: 30)')
        points=spec.get('points',[])
        if points:children.append(f'lq.scatter({nums([p["x"] for p in points])}, {nums([p["y"] for p in points])})')
        for point,label in zip(points,spec.get('labels',[])):
            children.append(f'lq.place({float(point["x"])}, {float(point["y"])}, pad(4pt, text({quote(label)})), align: left + bottom)')
    elif kind=='geometry_2d':
        for raw in spec.get('polygons', []):
            polygon=Polygon.model_validate(raw);points=polygon.vertices+[polygon.vertices[0]]
            children.append(f'lq.plot({nums([p.x for p in points])}, {nums([p.y for p in points])}, label: text({quote(polygon.label)}))')
    elif kind=='scatter':
        points=spec['points'];children.append(f'lq.scatter({nums([p["x"] for p in points])}, {nums([p["y"] for p in points])})')
    elif kind=='bar_chart':
        labels=spec['labels'];values=spec['values']
        if not labels or len(labels)!=len(values):raise ValueError('Barre non valide')
        children.append(f'lq.bar({nums(range(len(values)))}, {nums(values)})')
        limits[:2]=[-.5,len(values)-.5]
        for i,label in enumerate(labels):
            children.append(f'lq.place({float(i)}, 0, pad(3pt, text({quote(label)})), align: top)')
    else:raise ValueError('Tipo grafico non supportato')
    shape = 'width: 90mm, height: '+str(90*(limits[3]-limits[2])/(limits[1]-limits[0]))+'mm, margin: 0%, ' if kind=='geometry_2d' else 'width: 100%, height: 65mm, '
    return '#block(breakable: false)[#lq.diagram('+shape+'xlim: '+nums(limits[:2])+', ylim: '+nums(limits[2:])+', xlabel: text('+quote(spec.get('x_label',''))+'), ylabel: text('+quote(spec.get('y_label',''))+'), '+','.join(children)+')]'


def export(artifact):
    try:import typst
    except ImportError as e:raise ValueError('Installare typst dalle dipendenze del progetto') from e
    with tempfile.TemporaryDirectory(prefix='typst-') as folder:
        work=Path(folder);counter=0
        def math(latex,alt=''):
            nonlocal counter
            try:
                if not latex or len(latex)>20000:raise ValueError('Formula vuota o troppo lunga')
                run=subprocess.run([shutil.which('node') or 'node',str(ROOT/'renderer_tools/formula.cjs')],input=json.dumps({'latex':latex}),capture_output=True,text=True,encoding='utf8',timeout=20)
                if run.returncode:raise ValueError(run.stderr)
                data=json.loads(run.stdout);counter+=1;name=f'math-{counter}.svg'
                (work/name).write_text(data['svg'],encoding='utf8')
                return f'#box(image({quote(name)}, width: {min(data["width"]/4,430)}pt, alt: {quote(alt or latex)}))'
            except (ValueError,OSError,subprocess.TimeoutExpired) as error:
                logging.getLogger(__name__).warning("Rendering formula Typst fallito: %s; LaTeX=%r", error, latex)
                return '#text('+quote('[Formula non visualizzabile] '+(alt or latex))+')'
        def rich(value):
            if isinstance(value,dict):
                if 'segments' in value:
                    return ''.join(math(s.get('latex',''),s.get('alt_text','')) if s.get('type')=='formula' else rich(s.get('content','')) for s in value['segments'])
                return rich(value.get('content',''))
            text=str(value or '');out=[];cursor=0
            for match in _DELIMITED.finditer(text):
                out.append('#text('+quote(text[cursor:match.start()])+')')
                raw=match.group();n=2 if raw.startswith(('$$',r'\[',r'\(')) else 1
                out.append(math(raw[n:-n]));cursor=match.end()
            out.append('#text('+quote(text[cursor:])+')');return ''.join(out)
        source=['#import "@preview/lilaq:0.6.0" as lq', '#set page(paper: "a4", margin: 18mm, numbering: "1")', '#set text(font: "Libertinus Serif", size: 11pt, lang: "it")', '#set par(leading: .65em)', '#show heading: set text(fill: rgb("#12665e"))', '#heading(level: 1, '+quote(artifact.get('title','Documento'))+')']
        for c in artifact.get('sections',artifact.get('slides',[])):
            source.append('#heading(level: 2, '+quote(c.get('title',''))+')')
            for b in c.get('blocks',[]):
                kind=b.get('block_type','text')
                if kind=='graph':
                    try:source.append(plot(b))
                    except (ValueError,KeyError,SyntaxError,TypeError,OverflowError):source.append(rich('[Grafico non disponibile] '+b.get('alt_text','')))
                elif kind=='formula':source.append('#align(center)['+math(b.get('latex',''),b.get('alt_text',''))+']')
                elif kind=='list':
                    source.extend('#block['+rich('- ')+rich(item)+']' for item in b.get('items',[]))
                elif kind=='table':
                    rows=[b.get('headers',[])]+b.get('rows',[]);cols=max(map(len,rows),default=0)
                    if cols:source.append('#table(columns: '+str(cols)+', inset: 6pt, '+','.join('['+rich(cell)+']' for row in rows for cell in list(row)+['']*(cols-len(row)))+')')
                elif kind=='speaker_note':
                    if artifact.get('audience')!='students':source.append('#block(fill: rgb("#f0f5f4"), inset: 8pt)['+rich(b)+']')
                elif kind in ('image','image_request'):
                    from generated_assets import cached_image
                    asset=cached_image(b)
                    if asset:
                        counter+=1;name=f'image-{counter}.png';shutil.copyfile(asset.path,work/name)
                        source.append(f'#align(center)[#image({quote(name)}, width: {asset.width}pt, alt: {quote(asset.alt)})]')
                    else:source.append(rich('[Immagine non disponibile] '+b.get('alt_text','')))
                else:source.append(rich(b))
        (work/'main.typ').write_text('\n\n'.join(source),encoding='utf8')
        try:data=typst.compile(str(work/'main.typ'),root=str(work),package_cache_path=str(ROOT/'renderer_tools/typst-packages'))
        except Exception as e:raise ValueError('Rendering Typst non riuscito: '+str(e)) from e
    name=re.sub(r'[^\w .-]','_',artifact.get('filename_hint','artefatto')).rsplit('.',1)[0]
    return data,'application/pdf',name+'-typst.pdf'
