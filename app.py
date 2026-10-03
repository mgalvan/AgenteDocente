from __future__ import annotations

import tkinter as tk
from directives_store import load_directives
from tkinter import messagebox, ttk




class PromptComposer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Agente Docente | Compositore prompt")
        self.geometry("1280x820")
        self.minsize(980, 680)
        self.configure(bg="#f5faf9")

        self.catalogs = self.load_catalogs()
        self.class_var = tk.StringVar()
        self.artifact_var = tk.StringVar()
        self.lesson_type_var = tk.StringVar()
        self.lesson_topic_var = tk.StringVar()
        self.summary_class_var = tk.StringVar(value="Non selezionata")
        self.summary_artifact_var = tk.StringVar(value="Non selezionato")
        self.summary_detail_var = tk.StringVar(value="In attesa")
        self.prompt_text: tk.Text | None = None
        self.exercise_frame: ttk.Frame | None = None
        self.lesson_frame: ttk.Frame | None = None
        self.table_body: ttk.Frame | None = None
        self.rows: list[dict[str, tk.Variable]] = []

        self.setup_style()
        self.build_interface()

    @staticmethod
    def load_catalogs() -> dict[str, list[tuple[str, str]]]:
        directives = load_directives()
        groups = {"DET": [], "DED": [], "DBL": [], "DES": [], "DGT": []}
        for directive in directives:
            group = directive.get("Gruppo")
            if group in groups:
                groups[group].append((directive["Codice"], directive["Titolo"]))
        groups["DBL"] = [item for item in groups["DBL"] if item[0] in {"DBL02", "DBL03", "DBL04", "DBL05", "DBL06", "DBL07"}]
        return groups

    def setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#f5faf9")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Title.TLabel", background="#f5faf9", foreground="#1d2939", font=("Segoe UI", 26, "bold"))
        style.configure("Eyebrow.TLabel", background="#f5faf9", foreground="#e87957", font=("Segoe UI", 10, "bold"))
        style.configure("Muted.TLabel", background="#f5faf9", foreground="#667085", font=("Segoe UI", 10))
        style.configure("PanelTitle.TLabel", background="#ffffff", foreground="#1d2939", font=("Segoe UI", 15, "bold"))
        style.configure("Field.TLabel", background="#ffffff", foreground="#475467", font=("Segoe UI", 9, "bold"))
        style.configure("Section.TFrame", background="#e6f5f2", relief="solid", borderwidth=1)
        style.configure("SectionTitle.TLabel", background="#e6f5f2", foreground="#05645f", font=("Segoe UI", 11, "bold"))
        style.configure("Primary.TButton", background="#087f78", foreground="#ffffff", padding=(13, 9), font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#05645f")])
        style.configure("Secondary.TButton", background="#e6f5f2", foreground="#05645f", padding=(11, 8), font=("Segoe UI", 9, "bold"))
        style.configure("Tree.TFrame", background="#ffffff")
        style.configure("TreeHeader.TLabel", background="#eef4f3", foreground="#475467", font=("Segoe UI", 8, "bold"))

    def build_interface(self) -> None:
        outer = ttk.Frame(self, style="App.TFrame", padding=(28, 24))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 20))
        ttk.Label(header, text="AGENTE DOCENTE  /  DIRETTIVE 2.0", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(header, text="Costruisci la richiesta didattica.", style="Title.TLabel").pack(anchor="w", pady=(5, 3))
        ttk.Label(header, text="Definisci il contesto, scegli il formato e prepara un prompt strutturato per l'intelligenza artificiale.", style="Muted.TLabel").pack(anchor="w")

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content, style="Panel.TFrame", padding=22)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        right = ttk.Frame(content, style="Panel.TFrame", padding=22)
        right.grid(row=0, column=1, sticky="nsew")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        ttk.Label(left, text="Parametri della richiesta", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Separator(left).grid(row=1, column=0, sticky="ew", pady=(13, 18))
        fields = ttk.Frame(left, style="Panel.TFrame")
        fields.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        fields.columnconfigure(0, weight=1)
        fields.columnconfigure(1, weight=1)
        self.add_field(fields, "Classe *", self.class_var, ["1", "2", "3", "4", "5"], 0)
        self.add_field(fields, "Tipo di artefatto *", self.artifact_var, ["Lezione", "Esercizi", "Verifica sommativa"], 1)
        self.artifact_var.trace_add("write", lambda *_: self.update_mode())
        self.class_var.trace_add("write", lambda *_: self.update_summary())

        dynamic = ttk.Frame(left, style="Panel.TFrame")
        dynamic.grid(row=3, column=0, sticky="nsew")
        dynamic.columnconfigure(0, weight=1)
        dynamic.rowconfigure(0, weight=1)
        self.dynamic_container = dynamic
        self.update_mode()

        action_bar = ttk.Frame(left, style="Panel.TFrame")
        action_bar.grid(row=4, column=0, sticky="ew", pady=(19, 0))
        action_bar.columnconfigure(0, weight=1)
        ttk.Label(action_bar, text="La richiesta verra composta nel riepilogo.", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(action_bar, text="Prepara prompt AI", style="Primary.TButton", command=self.prepare_prompt).grid(row=0, column=1, sticky="e")

        ttk.Label(right, text="Riepilogo", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(right, text="Una vista rapida dei parametri che guideranno la generazione.", style="Muted.TLabel", wraplength=280).pack(anchor="w", pady=(6, 20))
        summary = tk.Frame(right, bg="#f6f8f8", highlightbackground="#e87957", highlightthickness=0, padx=15, pady=15)
        summary.pack(fill="x", anchor="n")
        tk.Label(summary, textvariable=self.summary_artifact_var, bg="#f6f8f8", fg="#1d2939", font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(0, 12))
        self.add_summary_line(summary, "Classe", self.summary_class_var)
        self.add_summary_line(summary, "Dettaglio", self.summary_detail_var)

    def add_field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, values: list[str], column: int) -> None:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 9, 9 if column == 0 else 0))
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=label, style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        combo = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly")
        combo.grid(row=1, column=0, sticky="ew")

    @staticmethod
    def add_summary_line(parent: tk.Frame, label: str, variable: tk.StringVar) -> None:
        line = tk.Frame(parent, bg="#f6f8f8")
        line.pack(fill="x", pady=3)
        tk.Label(line, text=label, bg="#f6f8f8", fg="#667085", font=("Segoe UI", 9)).pack(side="left")
        tk.Label(line, textvariable=variable, bg="#f6f8f8", fg="#344054", font=("Segoe UI", 9, "bold"), anchor="e", justify="right").pack(side="right", fill="x", expand=True)

    def update_mode(self) -> None:
        for child in self.dynamic_container.winfo_children():
            child.destroy()
        self.rows = []
        if self.artifact_var.get() == "Lezione":
            self.build_lesson_panel()
        elif self.artifact_var.get() in ("Esercizi", "Verifica sommativa"):
            self.build_exercise_panel()
        self.update_summary()

    def build_lesson_panel(self) -> None:
        panel = ttk.Frame(self.dynamic_container, style="Section.TFrame", padding=15)
        panel.grid(row=0, column=0, sticky="new")
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="Impostazioni della lezione", style="SectionTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 13))
        ttk.Label(panel, text="Tipo di lezione *", style="Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12))
        ttk.Combobox(panel, textvariable=self.lesson_type_var, values=["L1", "L2", "L3", "L4"], state="readonly", width=12).grid(row=2, column=0, sticky="ew", padx=(0, 12))
        ttk.Label(panel, text="Argomento della lezione *", style="Field.TLabel").grid(row=1, column=1, sticky="w")
        ttk.Entry(panel, textvariable=self.lesson_topic_var).grid(row=2, column=1, sticky="ew")
        self.lesson_type_var.trace_add("write", lambda *_: self.update_summary())
        self.lesson_topic_var.trace_add("write", lambda *_: self.update_summary())

    def build_exercise_panel(self) -> None:
        panel = ttk.Frame(self.dynamic_container, style="Section.TFrame", padding=12)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        title = "Configurazione della verifica" if self.artifact_var.get() == "Verifica sommativa" else "Configurazione degli esercizi"
        ttk.Label(panel, text=title, style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))

        table_holder = ttk.Frame(panel, style="Tree.TFrame")
        table_holder.grid(row=1, column=0, sticky="nsew")
        table_holder.rowconfigure(1, weight=1)
        headers = ["#", "Tipo esercizio", "N.", "Argomento", "Difficolta", "Livello cognitivo", "Soluzione", "Grafico"]
        column_widths = [30, 170, 48, 170, 130, 145, 150, 165]
        for column, (header, column_width) in enumerate(zip(headers, column_widths)):
            table_holder.columnconfigure(column, minsize=column_width, weight=0)
            ttk.Label(table_holder, text=header.upper(), style="TreeHeader.TLabel", padding=(4, 7)).grid(row=0, column=column, sticky="ew")
        body = ttk.Frame(table_holder, style="Tree.TFrame")
        body.grid(row=1, column=0, columnspan=len(headers), sticky="nsew")
        for column, column_width in enumerate(column_widths):
            body.columnconfigure(column, minsize=column_width, weight=0)
        self.table_body = body
        for index in range(10):
            variables: dict[str, tk.Variable] = {
                "det": tk.StringVar(), "count": tk.StringVar(), "topic": tk.StringVar(),
                "ded": tk.StringVar(), "dbl": tk.StringVar(), "des": tk.StringVar(), "dgt": tk.StringVar(),
            }
            self.rows.append(variables)
            ttk.Label(body, text=str(index + 1), foreground="#05645f", width=3, anchor="center").grid(row=index, column=0, padx=3, pady=2)
            self.add_combo(body, variables["det"], self.catalogs["DET"], index, 1, 22)
            self.add_entry(body, variables["count"], index, 2, 6, "1-9")
            self.add_entry(body, variables["topic"], index, 3, 22, "Argomento")
            self.add_combo(body, variables["ded"], self.catalogs["DED"], index, 4, 16)
            self.add_combo(body, variables["dbl"], self.catalogs["DBL"], index, 5, 18)
            self.add_combo(body, variables["des"], self.catalogs["DES"], index, 6, 19)
            self.add_combo(body, variables["dgt"], self.catalogs["DGT"], index, 7, 25)
            for variable in variables.values():
                variable.trace_add("write", lambda *_: self.update_summary())
        ttk.Label(panel, text="Compila solo le righe necessarie. Il prompt includera le righe con almeno un dato.", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))

    def add_combo(self, parent: ttk.Frame, variable: tk.Variable, catalog: list[tuple[str, str]], row: int, column: int, width: int) -> None:
        values = [f"{code} - {title}" for code, title in catalog]
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=width).grid(row=row, column=column, sticky="ew", padx=3, pady=2)

    @staticmethod
    def add_entry(parent: ttk.Frame, variable: tk.Variable, row: int, column: int, width: int, placeholder: str) -> None:
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.insert(0, "" if placeholder != "1-9" else "")
        entry.grid(row=row, column=column, sticky="ew", padx=3, pady=2)

    def update_summary(self) -> None:
        artifact = self.artifact_var.get()
        self.summary_class_var.set(self.class_var.get() or "Non selezionata")
        self.summary_artifact_var.set(artifact or "Nuova richiesta")
        if artifact == "Lezione":
            detail = self.lesson_type_var.get() or "Tipo da definire"
            if self.lesson_topic_var.get():
                detail += " / " + self.lesson_topic_var.get()
            self.summary_detail_var.set(detail)
        elif artifact in ("Esercizi", "Verifica sommativa"):
            filled = sum(bool(row["topic"].get() or row["det"].get() or row["count"].get()) for row in self.rows)
            self.summary_detail_var.set(f"{filled} righe compilate")
        else:
            self.summary_detail_var.set("In attesa")

    @staticmethod
    def extract_code(value: str) -> str:
        return value.split(" - ", 1)[0] if value else "[da scegliere]"

    def build_prompt(self) -> str:
        artifact = self.artifact_var.get() or "[da specificare]"
        lines = [
            "Agisci come docente di matematica per la scuola secondaria di secondo grado, indirizzo manutenzione ed assistenza tecnica.",
            f"Classe: {self.class_var.get() or '[da specificare]' }.",
            f"Artefatto richiesto: {artifact}.",
        ]
        if artifact == "Lezione":
            lines.extend([
                f"Tipo di lezione: {self.lesson_type_var.get() or '[da specificare]' }.",
                f"Argomento: {self.lesson_topic_var.get() or '[da specificare]' }.",
            ])
        elif artifact in ("Esercizi", "Verifica sommativa"):
            lines.append("Genera una verifica sommativa coerente come unico oggetto valutativo." if artifact == "Verifica sommativa" else "Genera gli esercizi richiesti come unita autonome.")
            for index, row in enumerate(self.rows, 1):
                values = {key: variable.get() for key, variable in row.items()}
                if any(values.values()):
                    count = values["count"] or "[da scegliere]"
                    lines.append(
                        f"Esercizio {index}: tipo {self.extract_code(values['det'])}; numero {count}; "
                        f"argomento {values['topic'] or '[da specificare]'}; difficolta {self.extract_code(values['ded'])}; "
                        f"livello cognitivo {self.extract_code(values['dbl'])}; soluzione {self.extract_code(values['des'])}; "
                        f"grafico {self.extract_code(values['dgt'])}."
                    )
        lines.append("Rispatta le direttive che sono state inviate con il prompt")
        return "\n".join(lines)

    def prepare_prompt(self) -> None:
        if not self.class_var.get() or not self.artifact_var.get():
            messagebox.showwarning("Dati mancanti", "Seleziona la classe e il tipo di artefatto.")
            return
        if self.artifact_var.get() == "Lezione" and (not self.lesson_type_var.get() or not self.lesson_topic_var.get().strip()):
            messagebox.showwarning("Dati mancanti", "Indica il tipo e l'argomento della lezione.")
            return
        prompt = self.build_prompt()
        if self.prompt_text is not None and self.prompt_text.winfo_exists():
            self.prompt_text.destroy()
        output = ttk.Frame(self.dynamic_container, style="Panel.TFrame")
        output.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        output.columnconfigure(0, weight=1)
        ttk.Label(output, text="Prompt pronto", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 7))
        ttk.Button(output, text="Copia prompt", style="Secondary.TButton", command=lambda: self.copy_prompt(prompt)).grid(row=0, column=1, sticky="e")
        self.prompt_text = tk.Text(output, height=10, wrap="word", relief="solid", borderwidth=1, font=("Segoe UI", 9), bg="#f8fafb", fg="#344054")
        self.prompt_text.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.prompt_text.insert("1.0", prompt)
        self.prompt_text.configure(state="disabled")

    def copy_prompt(self, prompt: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(prompt)
        self.update()
        messagebox.showinfo("Prompt copiato", "Il prompt e stato copiato negli appunti.")


if __name__ == "__main__":
    from webapp import run

    run()
