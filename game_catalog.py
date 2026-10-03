"""Game configuration derived exclusively from server directives."""
import re


def games_from_directives(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row['Gruppo'], []).append(row)
    games = []
    for group in sorted(groups):
        if not re.fullmatch(r'DGM[0-9]+', group):
            continue
        by_code = {r['Codice']: r for r in groups[group]}
        first, second = by_code.get(group+'01'), by_code.get(group+'02')
        if not first or not second:
            continue
        parameters = []
        seen = set()
        for match in re.finditer(r'\b(PAR(?:AM)?[0-9]+)\s*=\s*<([^<>]+)>', second['Direttiva completa'], re.I):
            code, label = match[1].upper(), match[2].strip()
            if code in seen:
                continue
            seen.add(code)
            options = [{'code': r['Codice'], 'title': r['Titolo']} for r in groups.get(label.upper(), [])]
            input_type = 'select' if options else ('number' if 'numero' in label.lower() and 'argomento' not in label.lower() else 'text')
            parameters.append({'code': code, 'label': label, 'options': options, 'input_type': input_type})
        games.append({'code': group, 'title': first['Titolo'], 'description': first['Direttiva completa'], 'parameters': parameters})
    return games


def validate_game(rows, code, values):
    game = next((g for g in games_from_directives(rows) if g['code'] == code), None)
    if game is None:
        raise ValueError('Selezionare un tipo di gioco disponibile.')
    if not isinstance(values, dict):
        raise ValueError('Parametri del gioco non validi.')
    selected = []
    lines = [f"Tipo di gioco: {'G' + game['code'][3:]} - {game['title']}"]
    for parameter in game['parameters']:
        value = values.get(parameter['code'], '')
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Compilare il parametro '+parameter['label'])
        value = value.strip()
        if parameter['input_type'] == 'number' and (not re.fullmatch(r'[0-9]+', value) or int(value) < 1):
            raise ValueError('Inserire un numero intero maggiore o uguale a 1 per '+parameter['label'])
        if parameter['options']:
            if value not in {o['code'] for o in parameter['options']}:
                raise ValueError('Scelta non valida per '+parameter['label'])
            selected.append(value)
        lines.append(f"{parameter['code']} ({parameter['label']}): {value}")
    return selected, '\n'.join(lines)
