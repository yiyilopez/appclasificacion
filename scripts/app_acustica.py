"""Sirve un prototipo local para analizar grabaciones de vigas."""
import argparse
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import find_peaks

from comparar_series_acusticas import compare, lab_examples
from acustica_materiales.modal import analyze_signal

APP = Path(__file__).resolve().parents[1] / 'app_acustica'
MAX_BYTES = 24 * 1024**2


def duration_ms(segment, background, fs):
    energy = np.maximum(segment**2 - np.mean(background**2), 0)
    cumulative = np.cumsum(energy)
    if cumulative[-1] <= 0:
        return None
    a, b = np.searchsorted(cumulative, cumulative[-1] * np.array([.05, .95]))
    return (b - a) * 1000 / fs


def analyze_audio(signal, fs):
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or not np.isfinite(x).all() or not 8000 <= fs <= 192000:
        raise ValueError('Usa un WAV con una frecuencia de muestreo entre 8 y 192 kHz.')
    if not 1.35 <= len(x) / fs <= 60:
        raise ValueError('El audio debe durar entre 1,35 y 60 segundos.')
    block = round(.005 * fs)
    frames = x[:len(x) // block * block].reshape(-1, block)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    background = float(np.quantile(rms, .2))
    peaks, _ = find_peaks(rms, distance=round(.75 * fs / block),
                          height=max(background * 6, float(rms.max()) * .04, 1e-7),
                          prominence=max(background * 3, float(rms.max()) * .025))
    events, durations = [], []
    end_previous = -fs
    for i in peaks:
        center = int(i) * block + block // 2
        radius = round(.012 * fs)
        lo, hi = max(0, center - radius), min(len(x), center + radius)
        peak = lo + int(np.argmax(np.abs(x[lo:hi])))
        if peak < round(.71 * fs) or len(x) - peak < round(.62 * fs):
            continue
        if peak - end_previous < round(.6 * fs):
            continue
        events.append({'pico_muestra': peak})
        end_previous = peak + round(.505 * fs)
        d90 = duration_ms(x[peak + round(.005 * fs):peak + round(.505 * fs)],
                          x[peak - round(.7 * fs):peak - round(.1 * fs)], fs)
        if d90 is not None:
            durations.append(float(d90))
    if not events:
        raise ValueError('No encontré un pulso con fondo y cola suficientes. Deja al menos un segundo de silencio antes y después de cada liberación.')
    frequencies, power, options, _ = analyze_signal(x, fs, events)
    eligible = sorted((row for row in options if row['cumple_criterios']),
                      key=lambda row: row['nivel_relativo_db'], reverse=True)
    best = eligible[0] if eligible else None
    max_power = max(float(np.max(power[frequencies <= 2000])), 1e-30)
    spectrum = [[float(f), float(10 * np.log10(max(p / max_power, 1e-6)))]
                for f, p in zip(frequencies[::4], power[::4]) if f <= 2000]
    warnings = []
    if len(events) == 1:
        warnings.append('Hay un solo pulso utilizable. Repite la liberación para evaluar si el pico se mantiene.')
    if len(events) < len(peaks):
        warnings.append('Algunos pulsos quedaron fuera por falta de silencio antes o después.')
    if not best:
        warnings.append('El audio no mostró un pico que superara el filtro de repetibilidad y ruido.')
    if np.max(np.abs(x)) >= .999:
        warnings.append('El audio alcanza el límite de amplitud. Revisa si hay saturación.')
    hz = best['frecuencia_hz'] if best else None
    return dict(frequency_hz=hz, wavelength_m=343 / hz if hz is not None else None,
                d90_ms=float(np.median(durations)) if durations else None,
                pulses=[round(row['pico_muestra'] / fs, 3) for row in events],
                support=best['pulsos_soporte'] if best else None,
                snr_db=best['snr_mediana_db'] if best else None,
                spectrum=spectrum,
                peaks=[dict(hz=row['frecuencia_hz'], snr_db=row['snr_mediana_db'],
                            support=row['pulsos_soporte']) for row in eligible[:6]],
                warnings=warnings)


class AppHandler(BaseHTTPRequestHandler):
    def send_data(self, status, content_type, data):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, payload):
        self.send_data(status, 'application/json; charset=utf-8',
                       json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())

    def do_GET(self):
        files = {'/': (APP / 'index.html', 'text/html; charset=utf-8'),
                 '/series.js': (APP / 'series.js', 'text/javascript; charset=utf-8'),
                 '/ejemplo.json': (APP / 'ejemplo.json', 'application/json; charset=utf-8')}
        if self.path == '/ejemplos':
            try:
                self.send_json(200, lab_examples())
            except FileNotFoundError:
                self.send_json(200, [])
            return
        target = files.get(self.path)
        if target and target[0].is_file():
            self.send_data(200, target[1], target[0].read_bytes())
        else:
            self.send_json(404, {'error': 'Archivo no disponible.'})

    def do_POST(self):
        if self.path == '/comparar':
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 32768:
                    raise ValueError('El tamaño de la serie no es válido.')
                points = json.loads(self.rfile.read(size))
                self.send_json(200, compare(points))
            except (ValueError, UnicodeDecodeError) as error:
                self.send_json(400, {'error': str(error)})
            return
        if self.path != '/analizar':
            self.send_json(404, {'error': 'Ruta no disponible.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BYTES:
                self.send_json(413, {'error': 'El archivo debe pesar menos de 24 MiB.'})
                return
            with sf.SoundFile(io.BytesIO(self.rfile.read(size))) as audio:
                if audio.format not in {'WAV', 'WAVEX', 'RF64'}:
                    raise ValueError('El prototipo admite archivos WAV.')
                if not 1.35 <= audio.frames / audio.samplerate <= 60:
                    raise ValueError('El audio debe durar entre 1,35 y 60 segundos.')
                if audio.channels not in {1, 2}:
                    raise ValueError('Usa una grabación mono o estéreo.')
                result = analyze_audio(audio.read(always_2d=True)[:, 0], audio.samplerate)
            self.send_json(200, result)
        except sf.LibsndfileError:
            self.send_json(400, {'error': 'No pude leer el archivo. Usa un WAV válido.'})
        except ValueError as error:
            self.send_json(400, {'error': str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), AppHandler) as server:
        print(f'Analizador acústico en http://127.0.0.1:{args.port}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
