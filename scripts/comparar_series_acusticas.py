"""Compara la dependencia entre una longitud medida y una frecuencia."""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import linregress

AN = Path(__file__).resolve().parents[1] / 'resultados/reglas_2026/analisis'


def compare(points):
    if not isinstance(points, list) or not 4 <= len(points) <= 30:
        raise ValueError('Incluye entre 4 y 30 longitudes distintas para comparar modelos.')
    if any(not isinstance(point, dict) for point in points):
        raise ValueError('Cada punto necesita una longitud y una frecuencia.')
    try:
        pairs = sorted((float(point['length_cm']), float(point['frequency_hz'])) for point in points)
    except (KeyError, ValueError, TypeError, OverflowError) as error:
        raise ValueError('Cada punto necesita una longitud y una frecuencia numéricas.') from error
    lengths, frequencies = np.array(pairs, dtype=float).T
    if not np.isfinite(pairs).all() or not (0.001 <= lengths[0] <= lengths[-1] <= 100000):
        raise ValueError('Introduce longitudes positivas entre 0,001 y 100 000 cm.')
    if np.any(frequencies < .01) or np.any(frequencies > 200000):
        raise ValueError('Introduce frecuencias entre 0,01 y 200 000 Hz.')
    if np.any(np.diff(lengths) <= 0):
        raise ValueError('Usa un solo punto por longitud. Si tienes repeticiones, usa una frecuencia representativa.')

    log_lengths, log_f = np.log(lengths), np.log(frequencies)
    grid = np.linspace(lengths[0], lengths[-1], 100)
    models = []
    for exponent, label in [(0, 'Constante'), (-1, 'Inversa (1/L)'), (-2, 'Inversa al cuadrado (1/L²)')]:
        intercepts = log_f - exponent * log_lengths
        omitted_errors = (intercepts.sum() - intercepts) / (len(pairs) - 1) - intercepts
        error = 100 * np.mean(np.abs(np.expm1(omitted_errors)))
        predicted = np.exp(intercepts.mean() + exponent * np.log(grid))
        models.append(dict(exponent=exponent, label=label, error_pct=float(error),
                           curve=list(zip(grid.tolist(), predicted.tolist()))))
    regression = linregress(log_lengths, log_f)
    return dict(points=pairs, exponent=float(regression.slope),
                r2=float(regression.rvalue**2) if np.ptp(log_f) > 0 else None,
                models=sorted(models, key=lambda model: model['error_pct']))


def lab_examples():
    with (AN / 'revision_modal/analisis_fisico.json').open() as source:
        records = json.load(source)['registros']
    with (AN / 'seguimiento_modos/seguimiento_ramas.json').open() as source:
        branches = json.load(source)['ramas']
    with (AN / 'seguimiento_guiado/seleccion_por_probeta.csv').open(encoding='utf-8-sig') as source:
        selected = {row['probeta'] for row in csv.DictReader(source)
                    if row['apta_para_contraste_exploratorio'] == 'True'}
    examples = []
    for branch in sorted(branches, key=lambda row: row['codigo']):
        if branch['rango'] == 1 and branch['codigo'] in selected:
            examples.append(dict(id=branch['codigo'] + '-rama', code=branch['codigo'],
                source='Seguimiento por continuidad', points=[dict(length_cm=p['L_cm'], frequency_hz=p['f'])
                                                              for p in branch['rama']]))
    for code in sorted({row['codigo_probeta'] for row in records}):
        examples.append(dict(id=code + '-picos', code=code, source='Picos dominantes por toma',
            points=[dict(length_cm=row['L_cm'], frequency_hz=row['frecuencia_dominante_hz']) for row in records
                    if row['codigo_probeta'] == code and row['frecuencia_dominante_hz'] is not None]))
    return examples
