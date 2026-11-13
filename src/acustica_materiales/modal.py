"""Detección de picos acústicos en pulsos de vibración libre."""

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks, peak_widths, periodogram, resample_poly

FS = 8000
NFFT = 32768
MIN_HZ, MAX_HZ = 8., 2000.
MIN_SNR_DB = 6.
MIN_REL_DB = -40.
MIN_LOCAL_PROMINENCE_DB = 6.
EPS = np.finfo(float).tiny
WINDOWS = ((.005, .5), (.020, .5), (.005, .25), (.005, .6))


def spectrum(signal):
    ramp = np.ones(len(signal))
    begin, end = round(.003 * FS), round(.015 * FS)
    ramp[:begin] = np.sin(np.linspace(0, np.pi / 2, begin))**2
    ramp[-end:] = np.cos(np.linspace(0, np.pi / 2, end))**2
    frequency, power = periodogram(signal, FS, window=ramp, detrend='linear', nfft=NFFT)
    power = gaussian_filter1d(power, 1.5 / (frequency[1] - frequency[0]))
    return frequency, power


def peaks_in_spectrum(frequency, corrected):
    band = (frequency >= MIN_HZ) & (frequency <= MAX_HZ)
    maximum = float(np.max(corrected[band]))
    if maximum <= 0:
        return []
    indices, properties = find_peaks(corrected, prominence=maximum * 1e-4,
                           height=maximum * 10**(MIN_REL_DB / 10),
                           distance=round(3 / (frequency[1] - frequency[0])),
                           wlen=round(100 / (frequency[1] - frequency[0])))
    local_floor = np.maximum(corrected[indices] - properties['prominences'], maximum * 1e-8)
    prominence_db = 10 * np.log10(np.maximum(corrected[indices], EPS) / local_floor)
    keep = band[indices] & (prominence_db >= MIN_LOCAL_PROMINENCE_DB)
    indices = indices[keep]
    prominence_db = prominence_db[keep]
    if not len(indices):
        return []
    widths = peak_widths(corrected, indices, rel_height=.5)[0] * (frequency[1] - frequency[0])
    return [dict(index=int(index), frequency_hz=float(frequency[index]), width_hz=float(width),
                 relative_db=float(10 * np.log10(max(corrected[index], EPS) / maximum)),
                 local_prominence_db=float(prominence))
            for index, width, prominence in zip(indices, widths, prominence_db, strict=True)]


def integrated_snr(frequency, power, noise, center, half_width):
    band = abs(frequency - center) <= half_width
    return float(10 * np.log10(max(float(power[band].sum()), EPS) /
                              max(float(noise[band].sum()), EPS)))


def analyze_signal(signal, original_fs, rows, name='audio', windows=WINDOWS):
    """Aplica el análisis espectral a muestras ya decodificadas."""
    divisor = math.gcd(original_fs, FS)
    x = resample_poly(signal, FS // divisor, original_fs // divisor)
    spectra, noises, corrected, peak_sets = [], [], [], []
    for event in rows:
        peak = round(int(event['pico_muestra']) / original_fs * FS)
        background = x[peak - round(.7 * FS):peak - round(.1 * FS)]
        if len(background) != round(.6 * FS):
            raise ValueError(f'Fondo incompleto en {name}')
        frequency, noise = spectrum(background)
        powers, excesses, peaks = [], [], []
        for delay, duration in windows:
            start = peak + round(delay * FS)
            signal = x[start:start + round(duration * FS)]
            if len(signal) != round(duration * FS):
                raise ValueError(f'Ventana incompleta en {name}')
            _, power = spectrum(signal)
            excess = np.maximum(power - noise, 0)
            powers.append(power)
            excesses.append(excess)
            peaks.append(peaks_in_spectrum(frequency, excess))
        spectra.append(powers)
        noises.append(noise)
        corrected.append(excesses)
        peak_sets.append(peaks)

    band = (frequency >= MIN_HZ) & (frequency <= MAX_HZ)
    normalized = [values[0] / max(float(values[0][band].sum()), EPS) for values in corrected]
    median_spectrum = np.median(normalized, axis=0)
    candidates = peaks_in_spectrum(frequency, median_spectrum)
    required = math.ceil(2 * len(rows) / 3)
    measured = []
    for candidate in candidates:
        center = candidate['frequency_hz']
        tolerance = max(3., .03 * center)
        half_width = max(3., candidate['width_hz'] / 2)
        supported, delayed, frequencies, snrs, deviations = 0, 0, [], [], []
        for powers, noise, peak_windows in zip(spectra, noises, peak_sets, strict=True):
            matches = [p for p in peak_windows[0] if abs(p['frequency_hz'] - center) <= tolerance]
            primary_snr = integrated_snr(frequency, powers[0], noise, center, half_width)
            snrs.append(primary_snr)
            if matches and primary_snr >= MIN_SNR_DB:
                supported += 1
                frequencies.append(min(matches, key=lambda p: abs(p['frequency_hz'] - center))['frequency_hz'])
            later = [p for p in peak_windows[1] if abs(p['frequency_hz'] - center) <= tolerance]
            later_snr = integrated_snr(frequency, powers[1], noise, center, half_width)
            if later and later_snr >= 3:
                delayed += 1
            for alternatives in peak_windows[2:]:
                near = [p for p in alternatives if abs(p['frequency_hz'] - center) <= 2 * tolerance]
                if near:
                    deviations.append(min(abs(p['frequency_hz'] - center) for p in near))
        acceptable = (supported >= required and delayed >= required and
                      candidate['width_hz'] <= .5 * center and center >= 10)
        measured.append(dict(archivo=name, frecuencia_hz=center, ancho_hz=candidate['width_hz'],
            nivel_relativo_db=candidate['relative_db'], snr_mediana_db=float(np.median(snrs)),
            prominencia_local_db=candidate['local_prominence_db'], contraste_lote_db=None,
            pulsos_soporte=supported, pulsos_cola_soporte=delayed, pulsos_totales=len(rows),
            dispersion_hz=float(np.std(frequencies, ddof=1)) if len(frequencies) > 1 else None,
            sensibilidad_max_hz=max(deviations) if deviations else None,
            cumple_criterios=acceptable,
            motivo='cumple' if acceptable else 'soporte_cola_anchura_o_borde_insuficiente'))
    eligible = [candidate for candidate in measured if candidate['cumple_criterios']]
    selected = min(eligible, key=lambda candidate: candidate['frecuencia_hz']) if eligible else None
    return frequency, median_spectrum, measured, selected
