'use strict';

const $ = id => document.getElementById(id);
const format = (n, unit, digits = 1) => n == null ? '—' : n.toLocaleString('es-CO', {maximumFractionDigits: digits, minimumFractionDigits: digits}) + (unit ? ' ' + unit : '');
let current = null;
let playerURL = null;
let currentName = '';

function drawSpectrum(data) {
  const canvas = $('spectrum');
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = w * ratio; canvas.height = h * ratio;
  const g = canvas.getContext('2d');
  g.scale(ratio, ratio);
  const left = 48, top = 17, right = w - 18, bottom = h - 37;
  const toX = f => left + f / 2000 * (right - left);
  const toY = db => bottom - (db + 60) / 60 * (bottom - top);
  g.font = '12px system-ui';
  g.lineWidth = 1;
  g.strokeStyle = '#d2ddd9'; g.fillStyle = '#4e656d';
  for (const db of [-60, -45, -30, -15, 0]) {
    g.beginPath(); g.moveTo(left, toY(db)); g.lineTo(right, toY(db)); g.stroke();
    g.fillText(String(db), 13, toY(db) + 4);
  }
  g.fillText('dB', 5, 13);
  for (const f of [0, 500, 1000, 1500, 2000]) {
    g.textAlign = 'center'; g.fillText(String(f), toX(f), bottom + 16);
  }
  g.fillText('Frecuencia (Hz)', (left + right) / 2, h - 3);
  g.beginPath();
  for (const [index, [f, db]] of data.spectrum.entries()) {
    if (index === 0) g.moveTo(toX(f), toY(db)); else g.lineTo(toX(f), toY(db));
  }
  g.strokeStyle = '#126351'; g.lineWidth = 1.3; g.stroke();
  if (data.frequency_hz != null) {
    g.beginPath(); g.setLineDash([5, 3]); g.strokeStyle = '#a75e16';
    const x = toX(data.frequency_hz);
    g.moveTo(x, top); g.lineTo(x, bottom); g.stroke();
  }
}

function show(result, name) {
  current = result;
  currentName = name;
  $('hz').textContent = format(result.frequency_hz, 'Hz');
  $('wavelength').textContent = format(result.wavelength_m, 'm', 2);
  $('duration').textContent = format(result.d90_ms, 'ms', 0);
  const count = result.pulses.length;
  $('quality').textContent = result.support == null ? count + ' pulsos analizados.' :
    'Pico dominante presente en ' + result.support + ' de ' + count + ' pulsos.';
  $('warnings').replaceChildren(...result.warnings.map(message => {
    const li = document.createElement('li'); li.textContent = message; return li;
  }));
  $('warnings').hidden = result.warnings.length === 0;
  const rows = result.peaks.map(peak => [format(peak.hz, 'Hz'), format(peak.snr_db, 'dB'), peak.support + '/' + count]);
  if (!rows.length) rows.push(['—', '—', '—']);
  $('peaks').replaceChildren(...rows.map(cells => {
    const tr = document.createElement('tr');
    cells.forEach(value => { const td = document.createElement('td'); td.textContent = value; tr.append(td); });
    return tr;
  }));
  $('results').hidden = false;
  $('result-peak').replaceChildren(...result.peaks.map((peak, index) => new Option(
    format(peak.hz, 'Hz') + (index === 0 ? ' · dominante' : ''), peak.hz)));
  $('add-result').hidden = !result.peaks.length;
  $('save-status').textContent = '';
  $('save-status').classList.remove('error');
  $('peak-picker').hidden = result.peaks.length < 2;
  $('audio-details').open = false;
  $('open-series').hidden = true;
  $('measured-length').value = '';
  if (activeView === 'audio') $('results').focus();
}

const points = [];
let activeView;
let seriesRevision = 0;
let exampleRequest;
let exampleResult;

function numberFrom(input) {
  const value = String(input).trim().replace(',', '.');
  return value ? Number(value) : NaN;
}

function invalidateSeries() {
  seriesRevision += 1;
  $('series-result').replaceChildren();
  $('series-status').textContent = '';
}

function renderPoints() {
  invalidateSeries();
  $('series-count').hidden = points.length === 0;
  $('series-count').textContent = '(' + points.length + ')';
  $('empty-series').hidden = points.length > 0;
  $('series-points').hidden = points.length === 0;
  $('compare-series').hidden = points.length < 4;
  $('add-row').disabled = points.length >= 30;
  $('series-progress').textContent = points.length >= 4
    ? points.length + ' mediciones en la serie.'
    : 'Faltan ' + (4 - points.length) + ' para comparar.';
  $('point-rows').replaceChildren(...points.map((point, index) => {
    const row = document.createElement('tr');
    row.insertCell().textContent = point.name;
    row.cells[0].className = 'row-label';
    for (const [key, label] of [['length_cm', 'Longitud'], ['frequency_hz', 'Frecuencia']]) {
      const input = document.createElement('input');
      input.inputMode = 'decimal';
      input.value = point[key];
      input.setAttribute('aria-label', label + ' de la medición ' + (index + 1));
      input.addEventListener('input', () => {
        point[key] = input.value;
        invalidateSeries();
      });
      row.insertCell().append(input);
    }
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'secondary';
    remove.textContent = 'Quitar';
    remove.setAttribute('aria-label', 'Quitar medición ' + (index + 1));
    remove.addEventListener('click', () => {
      points.splice(index, 1);
      renderPoints();
      const nextRow = $('point-rows').children[Math.min(index, points.length - 1)];
      (nextRow?.querySelector('button') || $('add-row')).focus();
    });
    row.insertCell().append(remove);
    return row;
  }));
}

function drawComparison(canvas, result) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const g = canvas.getContext('2d');
  g.scale(ratio, ratio);
  const left = 62, right = width - 18, top = 21, bottom = height - 46;
  const first = result.points[0][0], last = result.points.at(-1)[0];
  const [best] = result.models;
  const maximum = Math.max(...result.points.map(point => point[1]), ...best.curve.map(point => point[1]));
  const x = length => left + (length - first) / (last - first) * (right - left);
  const y = frequency => bottom - frequency / (maximum * 1.06) * (bottom - top);
  g.font = '12px system-ui';
  g.fillStyle = '#50625a';
  g.strokeStyle = '#d5dfd7';
  for (let i = 0; i <= 4; i++) {
    const value = maximum * i / 4;
    g.beginPath();
    g.moveTo(left, y(value));
    g.lineTo(right, y(value));
    g.stroke();
    g.fillText(value.toLocaleString('es-CO', {maximumSignificantDigits: 3}), 4, y(value) + 4);
  }
  g.fillText('Hz', 4, 13);
  g.textAlign = 'center';
  const tickCount = width < 340 ? 3 : 5;
  for (let i = 0; i < tickCount; i++) {
    const length = first + (last - first) * i / (tickCount - 1);
    g.fillText(length.toLocaleString('es-CO', {maximumSignificantDigits: 5}), x(length), bottom + 17);
  }
  g.fillText('Longitud libre (cm)', (left + right) / 2, height - 8);
  g.beginPath();
  g.strokeStyle = '#935018';
  g.lineWidth = 2;
  g.setLineDash([6, 4]);
  for (const [index, [length, frequency]] of best.curve.entries()) {
    if (index === 0) g.moveTo(x(length), y(frequency));
    else g.lineTo(x(length), y(frequency));
  }
  g.stroke();
  g.fillStyle = '#19543f';
  for (const [length, frequency] of result.points) {
    g.beginPath();
    g.arc(x(length), y(frequency), 4.5, 0, 2 * Math.PI);
    g.fill();
  }
}

function showComparison(container, result) {
  const article = $('comparison-template').content.firstElementChild.cloneNode(true);
  const [best] = result.models;
  const distance = Math.abs(result.exponent + 2);
  article.querySelector('.verdict').textContent = distance <= .2
    ? 'El exponente está cerca de −2'
    : 'El exponente se aleja de −2';
  article.querySelector('.reading').textContent = 'El ajuste dio ' +
    format(result.exponent, '', 2).replace('-', '−') + ', a ' + format(distance, '', 2) + ' del −2 teórico.';
  article.querySelector('.prediction').textContent = 'El modelo con menor error fue «' + best.label +
    '», con ' + format(best.error_pct, '%') + '.';
  const [startLength, startFrequency] = result.points[0];
  const [endLength, endFrequency] = result.points.at(-1);
  const expected = startFrequency * (startLength / endLength) ** 2;
  article.querySelector('.endpoints').textContent = 'De ' + format(startLength, 'cm', 1) + ' a ' +
    format(endLength, 'cm', 1) + ', la frecuencia pasó de ' + format(startFrequency, 'Hz', 0) + ' a ' +
    format(endFrequency, 'Hz', 0) + '. Si siguiera 1/L², llegaría a ' + format(expected, 'Hz', 0) + '.';
  article.querySelector('.chart-key').textContent = 'Puntos verdes: mediciones. Línea punteada: ' + best.label + '.';
  const table = article.querySelector('tbody');
  for (const model of result.models) {
    const row = table.insertRow();
    row.insertCell().textContent = model.label;
    row.insertCell().textContent = format(model.error_pct, '%');
  }
  const details = article.querySelector('details');
  const canvas = article.querySelector('canvas');
  details.addEventListener('toggle', () => { if (details.open) drawComparison(canvas, result); });
  container.replaceChildren(article);
  return article;
}

async function getJSON(path, options) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Ocurrió un error. Intenta de nuevo.');
  return result;
}

function compare(data) {
  return getJSON('comparar', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
}

async function compareSeries() {
  const data = points.map(point => ({
    length_cm: numberFrom(point.length_cm),
    frequency_hz: numberFrom(point.frequency_hz)
  }));
  const status = $('series-status');
  status.classList.remove('error');
  if (data.some(point => !Number.isFinite(point.length_cm) || !Number.isFinite(point.frequency_hz))) {
    status.textContent = 'Completa la longitud y la frecuencia de cada medición.';
    status.classList.add('error');
    return;
  }
  const version = seriesRevision;
  $('compare-series').disabled = true;
  status.textContent = 'Comparando frecuencias…';
  try {
    const result = await compare(data);
    if (version === seriesRevision) {
      status.textContent = '';
      const article = showComparison($('series-result'), result);
      if (activeView === 'serie') article.focus();
    }
  } catch (error) {
    if (version === seriesRevision) {
      status.textContent = error.message;
      status.classList.add('error');
    }
  } finally {
    $('compare-series').disabled = false;
  }
}

function loadExample() {
  if (exampleRequest || exampleResult) return;
  const status = $('example-status');
  status.classList.remove('error');
  status.textContent = 'Cargando el ejemplo…';
  exampleRequest = getJSON('ejemplo.json').then(compare).then(result => {
    exampleResult = result;
    showComparison($('example-result'), result);
    $('example-cta').hidden = false;
    status.textContent = '';
  }).catch(error => {
    status.textContent = error.message;
    status.classList.add('error');
  }).finally(() => { exampleRequest = null; });
}

function showView(focus = false) {
  const links = [...document.querySelectorAll('[data-view]')];
  const requested = location.hash.slice(1);
  activeView = links.some(link => link.dataset.view === requested) ? requested : 'audio';
  for (const link of links) {
    const selected = link.dataset.view === activeView;
    $(link.dataset.view).hidden = !selected;
    if (selected) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (activeView === 'ejemplo') loadExample();
  if (focus) {
    $(activeView).focus({preventScroll: true});
    window.scrollTo(0, 0);
  }
}

async function analyze(file) {
  const status = $('status');
  status.textContent = 'Analizando…';
  status.classList.remove('error');
  $('choose-file').disabled = true;
  $('results').hidden = true;
  current = null;
  if (playerURL) URL.revokeObjectURL(playerURL);
  playerURL = null;
  $('player').pause();
  $('player').removeAttribute('src');
  $('player').hidden = true;
  try {
    const result = await getJSON('analizar', {method: 'POST', body: file});
    playerURL = URL.createObjectURL(file);
    $('player').src = playerURL;
    $('player').hidden = false;
    status.textContent = '';
    show(result, file.name);
  } catch (error) {
    status.textContent = error.message || 'No se pudo analizar el audio.';
    status.classList.add('error');
  } finally {
    $('choose-file').disabled = false;
  }
}

$('choose-file').addEventListener('click', () => $('file').click());
$('file').addEventListener('change', () => {
  const file = $('file').files[0];
  if (!file) return;
  $('file').value = '';
  $('file-name').textContent = file.name;
  $('status').textContent = '';
  analyze(file);
});
$('save-point').addEventListener('click', () => {
  const length = numberFrom($('measured-length').value);
  const frequency = numberFrom($('result-peak').value);
  const status = $('save-status');
  status.classList.remove('error');
  if (!current || !(length >= .001 && length <= 100000 && frequency > 0)) {
    status.textContent = 'Ingresa la longitud libre en centímetros.';
    status.classList.add('error');
    return;
  }
  if (points.length >= 30 || points.some(point => numberFrom(point.length_cm) === length)) {
    status.textContent = 'Guarda una medición por longitud, hasta 30 por serie.';
    status.classList.add('error');
    return;
  }
  points.push({name: currentName, length_cm: length, frequency_hz: frequency});
  renderPoints();
  status.textContent = 'Medición guardada.';
  $('open-series').hidden = false;
});
$('add-row').addEventListener('click', () => {
  if (points.length >= 30) return;
  points.push({name: 'Manual', length_cm: '', frequency_hz: ''});
  renderPoints();
  $('point-rows').lastElementChild.querySelector('input').focus();
});
$('compare-series').addEventListener('click', compareSeries);
$('audio-details').addEventListener('toggle', () => {
  if (current && $('audio-details').open) drawSpectrum(current);
});
window.addEventListener('hashchange', () => {
  showView(true);
  if (activeView === 'audio' && current && $('audio-details').open) drawSpectrum(current);
});
const resize = new ResizeObserver(entries => {
  for (const entry of entries) {
    if (entry.contentRect.width && entry.target.id === 'spectrum' && current) drawSpectrum(current);
  }
});
resize.observe($('spectrum'));
showView();
