"""Active flat response contract shared by Gemini and server validation."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import math


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Segment(Model):
    kind: Literal["text", "formula"]
    value: str  # Literal text or literal LaTeX, never a formula ID.


class Text(Model):
    id: str
    segments: list[Segment]


class Formula(Model):
    id: str
    latex: str
    alt_text: str
    expression: str  # Empty when no computation is needed.


class Point(Model):
    x: float
    y: float


class Viewport(Model):
    x_min: float
    x_max: float
    y_min: float
    y_max: float


class Area(Model):
    expression: str
    x_start: float
    x_end: float
    baseline: float

    @model_validator(mode="after")
    def interval(self):
        if not self.expression.strip() or not all(math.isfinite(v) for v in (self.x_start, self.x_end, self.baseline)) or self.x_start >= self.x_end:
            raise ValueError("Area: espressione e intervallo finito crescente obbligatori.")
        return self


class Rectangles(Area):
    count: int
    sample: Literal["left", "right", "midpoint"]

    @model_validator(mode="after")
    def count_limit(self):
        if not 1 <= self.count <= 500:
            raise ValueError("Rettangoli: count deve essere tra 1 e 500.")
        return self


class Polygon(Model):
    vertices: list[Point]
    label: str

    @model_validator(mode="after")
    def valid_vertices(self):
        if len({(p.x, p.y) for p in self.vertices}) < 3 or not all(math.isfinite(p.x) and math.isfinite(p.y) for p in self.vertices):
            raise ValueError("Poligono: almeno tre vertici distinti e finiti.")
        return self


class CurvePiece(Model):
    expression: str
    x_start: float
    x_end: float
    start: Literal["open", "closed", "none"]
    end: Literal["open", "closed", "none"]
    holes: list[float]

    @model_validator(mode="after")
    def interval(self):
        if not self.expression.strip() or not all(math.isfinite(x) for x in [self.x_start,self.x_end]+self.holes) or self.x_start>=self.x_end:
            raise ValueError("Tratto: espressione e intervallo finito crescente obbligatori.")
        if any(not self.x_start < x < self.x_end for x in self.holes):
            raise ValueError("I buchi devono essere interni al tratto.")
        return self


class Graph(Model):
    id: str
    kind: Literal["function_2d", "scatter", "bar_chart", "geometry_2d"] = Field(description="geometry_2d is only for closed polygons with at least three vertices. Real-line intervals use function_2d with pieces: expression '0', explicit x_start/x_end and open/closed endpoints. Never encode intervals as geometry_2d or infer endpoint inclusion from alt_text.")
    expression: str
    points: list[Point]
    labels: list[str]
    values: list[float]
    viewport: Viewport
    x_label: str
    y_label: str
    alt_text: str
    pieces: list[CurvePiece] = Field(default_factory=list, description="Function pieces with explicit domains, endpoint markers and excluded x coordinates. When used, expression is empty. points are additional filled points. For a real-line interval [a,b), use expression '0', x_start=a, x_end=b, start='closed', end='open', holes=[]; leave graph expression, points, labels, values and polygons empty. Endpoint inclusion must be encoded here, not only in alt_text.")
    polygons: list[Polygon] = Field(default_factory=list, description="geometry_2d only: ordered polygon vertices and label; closing edge is automatic.")
    areas: list[Area] = Field(default_factory=list, description="Filled regions between expression and baseline on [x_start,x_end]. Use explicit data, not alt_text.")
    rectangles: list[Rectangles] = Field(default_factory=list, description="Equal-width Riemann rectangles on [x_start,x_end], with explicit count and left/right/midpoint sampling.")

    @model_validator(mode="after")
    def data_shape(self):
        if self.pieces and self.kind != "function_2d":
            raise ValueError("pieces richiede function_2d.")
        if self.kind == "geometry_2d":
            if not self.polygons or self.expression or self.points or self.labels or self.values:
                raise ValueError("geometry_2d: polygons obbligatorio; expression e altri dati vuoti.")
        elif self.polygons:
            raise ValueError("polygons richiede geometry_2d.")
        if self.kind != "function_2d" and (self.areas or self.rectangles):
            raise ValueError("Aree e rettangoli richiedono function_2d.")
        if self.kind == "function_2d":
            if bool(self.expression.strip()) == bool(self.pieces) or self.values:
                raise ValueError("function_2d: specificare expression oppure pieces, non entrambi; values vuoto.")
            if self.labels and len(self.labels) != (len(self.points) if self.points else (len(self.pieces) if self.pieces else len(self.expression.split(";")))):
                raise ValueError("function_2d: labels vuoto oppure una etichetta per punto; senza punti, una per curva.")
        if self.kind == "scatter" and (not self.points or self.expression or self.labels or self.values):
            raise ValueError("scatter: points obbligatorio; expression/labels/values vuoti.")
        if self.kind == "bar_chart" and (not self.labels or len(self.labels) != len(self.values) or self.expression or self.points):
            raise ValueError("bar_chart: labels/values di uguale lunghezza; expression/points vuoti.")
        return self


class GeneratedImage(Model):
    id: str
    generation_prompt: str
    alt_text: str


class ProvidedImage(Model):
    id: str
    resource_id: str
    alt_text: str


class CellSegment(Model):
    kind: Literal["text", "formula"]
    value: str  # Literal text or literal LaTeX, never an ID.


class TableCell(Model):
    # Blank body cells are intentional in worksheets and grading tables.
    segments: list[CellSegment]


class Cell(TableCell):
    @model_validator(mode="after")
    def nonempty(self):
        if not self.segments or not any(s.value.strip() for s in self.segments):
            raise ValueError("Voce/cella senza contenuto.")
        return self


class TextList(Model):
    id: str
    items: list[Cell]


class TextTable(Model):
    id: str
    headers: list[Cell]
    rows: list[list[TableCell]]

    @model_validator(mode="after")
    def rectangular(self):
        if not self.headers or any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError("Tabella: intestazioni obbligatorie e righe rettangolari.")
        return self


class BlockRef(Model):
    id: str = Field(description="Globally unique block identifier across the entire response, including resources, artifacts and containers. Use a block_ prefix. Must differ from ref; for example id=block_ex1_q, ref=text_ex1_q.")
    kind: Literal["text", "formula", "graph", "image", "list", "table", "speaker_note"]
    ref: str = Field(description="Identifier of the existing resource referenced by this block, selected by kind. This is the resource ID, not the block ID. Multiple blocks may reference the same resource, but must have distinct block IDs.")


class Container(Model):
    id: str
    title: str
    blocks: list[BlockRef]


class Artifact(Model):
    id: str
    kind: Literal["teacher_guide", "student_presentation", "exercise_sheet", "student_test", "teacher_solution"]
    audience: Literal["teacher", "students"]
    format: Literal["pdf", "pptx", "docx"]
    title: str
    containers: list[Container]  # Ordered sections for PDF/DOCX, slides for PPTX.


class Question(Model):
    id: str
    question: str
    required: bool


class Summary(Model):
    complete: bool
    audience_checked: bool
    math_checked: bool


class FlatResponse(Model):
    contract_version: Literal["setupgemma_flat_2.1"]
    status: Literal["complete", "needs_clarification"]
    request_type: str
    artifacts: list[Artifact]
    texts: list[Text]
    formulas: list[Formula]
    graphs: list[Graph]
    generated_images: list[GeneratedImage]
    provided_images: list[ProvidedImage]
    lists: list[TextList]
    tables: list[TextTable]
    questions: list[Question]
    validation_summary: Summary

    @model_validator(mode="after")
    def references(self):
        if self.status == "complete" and (not self.artifacts or self.questions):
            raise ValueError("complete: artifacts obbligatori, questions vuoto.")
        if self.status == "needs_clarification" and (self.artifacts or not self.questions):
            raise ValueError("needs_clarification: questions obbligatorie, artifacts vuoto.")
        all_ids = set()
        def register(item):
            if not item.id.strip() or item.id in all_ids:
                raise ValueError(f"Identificatore vuoto o duplicato: {item.id!r}.")
            all_ids.add(item.id)
        collections = {"text": self.texts, "formula": self.formulas, "graph": self.graphs,
                       "image": self.generated_images + self.provided_images, "list": self.lists, "table": self.tables}
        ids = {}
        for kind, collection in collections.items():
            for item in collection:
                register(item)
            ids[kind] = {item.id for item in collection}
        ids["speaker_note"] = ids["text"]
        def require(kind, ref):
            if ref not in ids[kind]:
                raise ValueError(f"Riferimento {kind} inesistente: {ref}.")
        for text in self.texts:
            if not text.segments:
                raise ValueError(f"Testo senza segments: {text.id}.")
        for artifact in self.artifacts:
            register(artifact)
            if not artifact.containers:
                raise ValueError("Artefatto senza sezioni/slide.")
            for container in artifact.containers:
                register(container)
                if not container.blocks:
                    raise ValueError("Sezione/slide senza contenuto.")
                for block in container.blocks:
                    if block.id == block.ref:
                        raise ValueError(
                            f"Il blocco {block.id!r} usa lo stesso identificatore della risorsa richiamata. "
                            "block.id deve essere distinto da block.ref (esempio: block_ex1_q e text_ex1_q). "
                            "Il contenuto resta esportabile tramite il riferimento alla risorsa."
                        )
                    register(block)
                    require(block.kind, block.ref)
        for question in self.questions:
            register(question)
        return self


def serving_schema():
    # Equivalent spellings/annotations only. No field or type is dropped.
    def adapt(value):
        if isinstance(value, list):
            return [adapt(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, child in value.items():
            if key == "title":
                continue
            if key == "const":
                result["enum"] = [child]
            elif key in {"properties", "$defs"}:
                result[key] = {name: adapt(schema) for name, schema in child.items()}
            else:
                result[key] = adapt(child)
        return result
    return adapt(FlatResponse.model_json_schema())


def response_json_schema():
    return FlatResponse.model_json_schema()


if __name__ == "__main__":
    import json
    from pathlib import Path
    Path("api_response.schema.json").write_text(json.dumps(response_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
