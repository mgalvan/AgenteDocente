"""Server validation and prompt for DGM01 exercise configuration."""
import re


def compose_exercises(rows, parameters, directives):
    count = str(parameters.get('PAR02', ''))
    if not re.fullmatch(r'[0-9]+', count) or not isinstance(rows, list) or len(rows) != int(count) or not rows:
        raise ValueError('DGM01: il numero di righe deve corrispondere a PAR02.')
    groups = {group: {d['Codice'] for d in directives if d['Gruppo'] == group} for group in ('DET','DED','DBL','DES','DGT')}
    lines = ['Genera gli esercizi richiesti come unità autonome.']
    codes = []
    common_topic = parameters.get('PAR01', '')
    if not isinstance(common_topic, str): raise ValueError('Argomento comune non valido.')
    common_topic = common_topic.strip()
    if not common_topic: raise ValueError('Compilare PAR01: argomento matematico.')
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict): raise ValueError('Riga esercizio non valida.')
        if common_topic: row = dict(row, topic=common_topic)
        for key in ('det','topic','ded','dbl','des'):
            if not isinstance(row.get(key), str) or not row[key].strip(): raise ValueError(f'Compilare {key} nella riga {i}.')
        for key, group in (('det','DET'),('ded','DED'),('dbl','DBL'),('des','DES'),('dgt','DGT')):
            value = row.get(key, '')
            if key == 'dgt' and not value: continue
            if value not in groups[group]: raise ValueError(f'Direttiva {group} non valida nella riga {i}.')
            codes.append(value)
        line = f"Esercizio {i}: tipo {row['det']}; argomento {row['topic'].strip()}; difficoltà {row['ded']}; livello cognitivo {row['dbl']}; soluzioni {row['des']}"
        if row.get('dgt'): line += '; grafico '+row['dgt']
        lines.append(line+'.')
    return codes, '\n'.join(lines)
