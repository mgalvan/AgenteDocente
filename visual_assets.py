"""Cached offline math/graph images. No Gemini calls and no eval."""
import ast
import base64
import hashlib
import json
import operator
import re
from pathlib import Path
import shutil
import subprocess
import threading
from dataclasses import dataclass
import numpy as np

CACHE = Path(__file__).resolve().parent / '.render_cache'
_LOCK = threading.RLock()


@dataclass
class Asset:
    path: Path
    width: float  # points, 72 per inch
    height: float
    alt: str


def formula(latex, alt='', display=True):
    latex = str(latex).strip()
    if not latex or len(latex)>20000:
        raise ValueError('Formula vuota o troppo lunga')
    key=hashlib.sha256(('mathjax3:'+str(display)+latex).encode()).hexdigest()
    with _LOCK:
        CACHE.mkdir(exist_ok=True)
        path=CACHE/(key+'.png');meta=CACHE/(key+'.json')
        if path.exists() and meta.exists():
            size=json.loads(meta.read_text())
        else:
            node=shutil.which('node')
            if not node:raise ValueError('Node.js necessario per il renderer matematico')
            run=subprocess.run([node,str(Path(__file__).parent/'renderer_tools/formula.cjs')],input=json.dumps({'latex':latex,'display':display}),capture_output=True,text=True,encoding='utf-8',timeout=20)
            if run.returncode:raise ValueError(run.stderr.strip() or 'Rendering formula fallito')
            result=json.loads(run.stdout);path.write_bytes(base64.b64decode(result['png']))
            size=[result['width']/4,result['height']/4];meta.write_text(json.dumps(size))
    return Asset(path,*size,alt or latex)


def evaluate_expression(expression, x):
    # An explicit function label is notation, not a Python assignment.
    expression = re.sub(r'^\s*(?:y|f\s*\(\s*x\s*\))\s*=(?!=)\s*', '', expression).strip()
    # Accept numeric coefficients such as 2x, without executing input code.
    expression = re.sub(r'(?<=\d)x\b', '*x', expression)
    tree=ast.parse(expression.replace('^','**'),mode='eval')
    if sum(1 for _ in ast.walk(tree))>150:raise ValueError('Espressione troppo complessa')
    functions={'sin':np.sin,'cos':np.cos,'tan':np.tan,'sqrt':np.sqrt,'exp':np.exp,'log':np.log,'ln':np.log,'abs':np.abs,'asin':np.arcsin,'acos':np.arccos,'atan':np.arctan}
    operators={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow}
    def visit(node):
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            if abs(node.value)>1e6:raise ValueError('Costante troppo grande')
            return float(node.value)
        if isinstance(node,ast.Name) and node.id in ('x','pi','e'):return {'x':x,'pi':np.pi,'e':np.e}[node.id]
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):return visit(node.operand)*(1 if isinstance(node.op,ast.UAdd) else -1)
        if isinstance(node,ast.BinOp) and type(node.op) in operators:
            left,right=visit(node.left),visit(node.right)
            if isinstance(node.op,ast.Pow) and np.any(np.abs(right)>100):raise ValueError('Esponente troppo grande')
            return operators[type(node.op)](left,right)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in functions and len(node.args)==1 and not node.keywords:return functions[node.func.id](visit(node.args[0]))
        raise ValueError('Espressione grafica non supportata')
    with np.errstate(all='ignore'):
        return np.broadcast_to(visit(tree.body),x.shape).astype(float).copy()


def graph_curves(expression, limits):
    """Explicit curves separated by semicolons, optionally restricted to an interval."""
    expressions = expression.split(';')
    if not 1 <= len(expressions) <= 20:
        raise ValueError('Numero di curve non supportato')
    number = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
    interval = re.compile(rf'(.+?)\s+for\s+x\s+in\s+\[\s*({number})\s*,\s*({number})\s*\]')
    curves = []
    for source in expressions:
        source = source.strip()
        left, right = limits[:2]
        match = interval.fullmatch(source)
        if match:
            source, start, end = match.groups()
            start, end = float(start), float(end)
            if not np.isfinite([start, end]).all() or start >= end:
                raise ValueError('Intervallo della curva non valido')
            left, right = max(left, start), min(right, end)
        # Validate even curves outside the viewport.
        x = np.linspace(left, max(left, right), 1400)
        y = evaluate_expression(source, x)
        if left >= right:
            continue
        y[~np.isfinite(y)] = np.nan
        jumps = np.flatnonzero(np.abs(np.diff(y)) > 2*(limits[3]-limits[2]))
        y[jumps] = np.nan
        curves.append((source, x, y))
    return curves


def resolved_curves(spec, limits):
    from models_api_flat import CurvePiece
    if not spec.get('pieces'):
        return graph_curves(spec.get('expression',''),limits), []
    curves=[];markers=[]
    for raw in spec['pieces']:
        p=CurvePiece.model_validate(raw)
        boundaries=[p.x_start]+sorted(set(p.holes))+[p.x_end]
        runs=[]
        for left,right in zip(boundaries,boundaries[1:]):
            lo,hi=max(left,limits[0]),min(right,limits[1])
            if lo>=hi:continue
            runs.extend(graph_curves(p.expression,[lo,hi,*limits[2:]]))
        if runs:
            curves.append((p.expression,np.concatenate([np.r_[x,np.nan] for _,x,y in runs]),np.concatenate([np.r_[y,np.nan] for _,x,y in runs])))
        for x,state in [(p.x_start,p.start),(p.x_end,p.end)]+[(x,'open') for x in p.holes]:
            if state=='none' or not limits[0]<=x<=limits[1]:continue
            y=float(evaluate_expression(p.expression,np.array([x]))[0])
            if np.isfinite(y):markers.append((x,y,state))
    return curves,markers


def draw_overlays(ax, spec):
    from models_api_flat import Area, Rectangles
    for raw in spec.get('areas', []):
        area = Area.model_validate(raw)
        x = np.linspace(area.x_start, area.x_end, 1400)
        y = evaluate_expression(area.expression, x)
        if not np.isfinite(y).all():
            raise ValueError('Area: funzione non finita nell’intervallo')
        ax.fill_between(x, area.baseline, y, color='#087f78', alpha=.22)
    for raw in spec.get('rectangles', []):
        rect = Rectangles.model_validate(raw)
        edges = np.linspace(rect.x_start, rect.x_end, rect.count+1)
        width = (rect.x_end-rect.x_start)/rect.count
        offset = {'left': 0, 'right': 1, 'midpoint': .5}[rect.sample]
        y = evaluate_expression(rect.expression, edges[:-1]+offset*width)
        if not np.isfinite(y).all():
            raise ValueError('Rettangoli: funzione non finita nei punti di campionamento')
        ax.bar(edges[:-1], y-rect.baseline, width=width, bottom=rect.baseline,
               align='edge', color='#edab45', edgecolor='#805300', alpha=.4, linewidth=.6)


def graph(spec):
    key=hashlib.sha256(('graph8:'+json.dumps(spec,sort_keys=True)).encode()).hexdigest()
    with _LOCK:
        CACHE.mkdir(exist_ok=True);path=CACHE/(key+'.png')
        if not path.exists():
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            vp=spec.get('viewport',{})
            limits=[float(vp[k]) for k in ('x_min','x_max','y_min','y_max')]
            if not all(np.isfinite(limits)) or limits[0]>=limits[1] or limits[2]>=limits[3]:raise ValueError('Limiti grafico non validi')
            fig=Figure(figsize=(6,3.6),dpi=200,layout='constrained');FigureCanvasAgg(fig);ax=fig.add_subplot()
            kind=spec.get('kind',spec.get('renderer',''))
            if kind=='function_2d':
                draw_overlays(ax, spec)
                curves,markers = resolved_curves(spec, limits)
                for i, (source, x, y) in enumerate(curves):
                    labels=spec.get("labels",[]) if not spec.get("points") else []
                    ax.plot(x,y,linewidth=1.8,label=labels[i] if i<len(labels) else source)
                if len(curves)>1 or (spec.get("labels") and not spec.get("points")):ax.legend(fontsize=7,loc='best')
                for x,y,state in markers:
                    ax.scatter([x],[y],facecolors='white' if state=='open' else '#222222',edgecolors='#222222',s=90,linewidths=1.5,zorder=10)
                points=spec.get('points',[])
                if points:ax.scatter([p['x'] for p in points],[p['y'] for p in points],color='#222222',zorder=4)
                for point, label in zip(points, spec.get('labels', [])):
                    ax.annotate(label, (point['x'], point['y']), xytext=(4, 6), textcoords='offset points')
            elif kind=='geometry_2d':
                from models_api_flat import Polygon
                for raw in spec.get('polygons', []):
                    polygon=Polygon.model_validate(raw)
                    points=polygon.vertices+[polygon.vertices[0]]
                    ax.plot([p.x for p in points], [p.y for p in points], label=polygon.label)
                ax.set_aspect('equal', adjustable='box');ax.legend(fontsize=7)
            elif kind=='scatter':
                points=spec.get('points',[])
                ax.scatter([p['x'] for p in points],[p['y'] for p in points],color='#087f78')
            elif kind=='bar_chart':
                labels,values=spec.get('labels',[]),spec.get('values',[])
                if not labels or len(labels)!=len(values):raise ValueError('Dati a barre non validi')
                ax.bar(labels,values,color='#087f78')
            else:raise ValueError('Tipo di grafico non supportato')
            if kind!='bar_chart':ax.set_xlim(*limits[:2])
            ax.set_ylim(*limits[2:]);ax.grid(True,alpha=.25);ax.set_xlabel(spec.get('x_label',''));ax.set_ylabel(spec.get('y_label',''))
            fig.savefig(path,dpi=200)
    return Asset(path,360,216,spec.get('alt_text','Grafico'))
