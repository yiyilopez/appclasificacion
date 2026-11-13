# appclasificacion

App de clasificación

## Laboratorio acústico de vigas

Aplicación en español para medir el sonido de una viga y estudiar cómo cambia
su frecuencia al variar la longitud libre. Se ejecuta localmente con Python 3.11
o posterior.

### Abrir la app

Clona el repositorio y crea un entorno virtual.

```sh
git clone https://github.com/yiyilopez/appclasificacion.git
cd appclasificacion
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python scripts/app_acustica.py
```

En Windows PowerShell, activa el entorno con `.venv\Scripts\Activate.ps1`.

Abre [la app local](http://127.0.0.1:8765/). El servidor procesa los audios en
memoria en tu equipo.

### Cómo usarla

1. En **Analizar audio**, selecciona un WAV. La app muestra la frecuencia dominante,
   la duración D90 y la longitud de onda estimada en el aire. Abre **Escuchar y
   revisar los picos** para ver el espectro o escoger otro pico.
2. Para comparar longitudes, guarda la frecuencia con la longitud libre en cm.
   Repite con la misma viga y el mismo tipo de apoyo. Si ya conoces las frecuencias,
   agrégalas directamente en **Comparar longitudes**.
3. Con cuatro longitudes distintas, elige **Comparar frecuencias**. La app muestra
   el exponente ajustado y compara tres modelos (constante, 1/L y 1/L²). El error
   se calcula prediciendo cada longitud con las demás.

**Ejemplo** muestra la probeta de madera MD03 del laboratorio. Sus cinco
frecuencias se obtuvieron siguiendo un pico entre 5 y 9 cm. El ajuste dio
−1,91 y el modelo 1/L² obtuvo el menor error de predicción (2,3 %).
La app usa una distancia de hasta 0,20 respecto de −2 como guía de lectura.
Interpretar el exponente requiere seguir un mismo modo de vibración. Las
mediciones de tu serie se mantienen al cambiar de vista y se borran al recargar.

El analizador admite WAV mono o estéreo de hasta 60 s y 24 MiB. Para grabar,
deja un segundo de silencio antes y después de cada liberación.
