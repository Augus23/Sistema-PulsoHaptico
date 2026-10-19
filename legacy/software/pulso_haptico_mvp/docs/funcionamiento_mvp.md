# Flujo general del sistema

Este documento explica paso a paso el funcionamiento de las partes más importantes del sistema.

## Cálculo del BPM

1. Arduino lee la señal analógica proveniente del Pulse Sensor Amped cada 10 ms.

2. La señal se suaviza mediante un filtro exponencial para reducir ruido.
3. Cada 3 segundos se calcula la amplitud observada entre el valor mínimo y máximo de la señal.
4. Si la amplitud es suficiente, se generan dos umbrales dinámicos:
   - `thresholdHigh = windowMin + amplitud × 0.60`
   - `thresholdLow = windowMin + amplitud × 0.40`
5. Un latido se detecta cuando la señal supera el umbral alto.
6. Para evitar doble conteo, la señal debe volver a bajar por debajo del umbral bajo antes de permitir una nueva detección.
7. Cuando se detectan dos latidos consecutivos se calcula el IBI (Inter Beat Interval).
8. El BPM se obtiene mediante la fórmula: `BPM = 60000 / IBI`.
9. Si el BPM calculado está fuera del rango fisiológico permitido (40 a 180 BPM), se descarta.
10. Los BPM válidos se almacenan en un buffer circular de 8 muestras.
11. El BPM final utilizado por el sistema (`beatAvg`) se obtiene promediando dichas muestras.

## Cómo se determina y comunica el estado

1. Durante los primeros 3 minutos se obtiene la línea base (baseline) del usuario.

2. Cada segundo se almacena una muestra de `beatAvg`.
3. Al finalizar la medición se calcula la mediana de todas las muestras obtenidas.
4. El resultado se almacena como `baselineBpm` y representa el BPM de referencia personal del usuario.
5. Una vez obtenido el baseline, el sistema comienza a evaluar el estado fisiológico.
6. Cada segundo se almacena el `beatAvg` en una ventana deslizante de 15 segundos.
7. Se calcula la mediana de dicha ventana y se obtiene `smoothBpm`.
8. Se calcula la diferencia respecto al baseline: `delta = smoothBpm - baselineBpm`.
9. Según el valor de delta se determina el nivel actual:
   - `delta < 9` → **reassure** (incluye valores negativos: el usuario está más tranquilo que su baseline)
   - `delta entre 9 y 18` → **awareness**
   - `delta entre 19 y 32` → **breath**
   - `delta >= 33` → **calm_down**
10. Si el nivel actual es **diferente al nivel anterior** (`currentLevel != lastEventLevel`), Arduino emite el evento: `EVT,policy_change`.
11. La aplicación Python recibe dicho evento y envía el patrón háptico correspondiente a la política detectada.
12. Además, Arduino envía periódicamente telemetría mediante mensajes `TEL` para informar BPM, baseline, delta, nivel y política actual.
</details>

## Cómo la app de Python recibe datos

1. La aplicación establece conexión con el Arduino utilizando un `puerto serie` mediante el cual se transmite la información de forma secuencial y bidireccional.

2. Luego de abrir la conexión serial, se resetea el buffer de input para vaciarlo y se informa en pantalla que la conexión fue establecida correctamente.
3. El código emplea un loop para leer constantemente la información enviada desde el Arduino.
   Una vez leídos los datos los decodifica y limpia, transformándolos de byte a string y haciendo uso de medidas de seguridad para reemplazar los bytes corruptos, en caso de que hubiera, por signos de interrogación.
4. Cuando se termina de realizar la limpieza de los datos se imprime en pantalla la telemetría recibida.

## Cómo la app de Python elige una política

1. Si la telemetría recibida corresponde a la fase de inferencia y hay buena señal, la aplicación verifica el modo de procesamiento de política:
   - `modo = "arduino"`: devuelve la política determinada por el código Arduino, siempre y cuando exista en su propia lista de políticas.

   - `modo = "pc"`: la aplicación elige una política de acuerdo a sus propios criterios. Para llevar esto a cabo extrae el **bpm suavizado** y el **baseline bpm** de la telemetría con el objetivo de calcular el delta (diferencia entre los latidos actuales y los latidos en reposo).

     Una vez calculado el delta, elige una política en base a dicho valor:
     - `delta < 9` → **reassure**
     - `delta entre 9 y 18` → **awareness**
     - `delta entre 19 y 32` → **breath**
     - `delta >= 33` → **calm_down**

## Cómo se traduce un patron JSON a datos enviados por USB

Los patrones hapticos se almacenan en formato JSON en la PC para poder editarlos facilmente.

Como Arduino Nano tiene recursos limitados, la PC convierte cada patron JSON en un `protocolo serial compacto` antes de enviarlo por USB.

La funcion responsable de la traduccion es: `build_effective_pattern()`:

1. Recibe:
   - 1.1) `pattern` -> JSON cargado desde el catalogo
   - 1.2) `intensity_overrides` -> Personalizaciones de Intensidad
   - 1.3) `duration_Overrides` -> Personalizaciones de duracion
   - 1.4) `repeat_Overrides` -> personalizaciones de repeticiones

2. Identifica la politica usando: policy = pattern["context"]["policy"].
3. Se leen los limites definidos en el JSON (Cosas que se pueden personalizar y cosas que no): adjustable = pattern ["adjustable_params"].
4. Se aplican las personalizaciones pedidas por el usuario, si el usuario no pidio ninguna se usan las del JSON por defecto.
5. Como arduino recibe numeros se convierte la politica a valores numericos (codigo).
6. Se crea la primera linea del protocolo: PATTERN {politica, personalizado, repeticiones, Cooldown, Pasos}.
7. Recorre todos los pasos: Cada objeto JSON dentro de steps se convierte en un comando serial.
8. Traduce la duracion (Puede escalarse) -> duration_ms = int[step("duration_ms"] * duration_scale): por ejemplo: 200*1.25 = 250ms (valor que recibe arduino).
9. Traducir intensidad a PWM: Arduino controla motores usando PWM de 0 a 255, JSON usa valores de 0 a 1.
10. Traducir canales a mascara binaria -> JSON: [1,0,0,0,0,1] -> Significa motor 0 y 5 activos.
11. Traducir Transicion.
12. Construye el comando STEP con todos los datos traducidos: STEP,{duration_ms},{mask},{pwm},{transition_code}.
13. Repite para todos los pasos (Para cada step).
14. Cierra con END al terminar -> commands.append("END").
15. La funcion devuelve un objeto de tipo `EffectivePattern`.
16. Luego la funcion `send_effective_pattern()` toma la lista y la envia por USB.

Los `steps` son instrucciones que forman un patron haptico (pasos de una secuencia de vibracion) -> ¿Que motores deben vibrar, con que intensidad y por cuanto tiempo?

## Cómo Arduino ejecuta la vibracion

1. El arduino recibe el patrón y guarda los datos.

2. Luego le llegan los pasos a hacer del patrón y con END se termina la comunicación.
3. En el loop se ejecuta el `updateHapticPlayback()`, para ir actualizando los valores
   - 3.1) Toma el paso actual
   - 3.2) Calcula el tiempo que paso
   - 3.3) Y calcula el PWM a usar (constante, ir subiendo gradualmente, ir bajando gradualmete)

4. Activamos los motores que queremos usar y a la intensidad que queremos.
5. Una vez que se termina de ejecutar el paso, se pasa al siguiente.
6. Esto se repite por cuantos pasos tenga el patron y repeticiones de estos.
7. Una vez que termina, se apagan todos los motores.
