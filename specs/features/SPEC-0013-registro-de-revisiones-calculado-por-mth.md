# SPEC-0013 · Registro de revisiones calculado por mth

- Estado: implementada
- Fecha: 2026-11-23
- ADRs: [ADR-0008](../adr/process/ADR-0008-catalogo-de-plantillas-de-agentes.md)
- Sustituye a: la parte de [SPEC-0001](SPEC-0001-delegacion-verificable.md) que toma los bloqueantes de la última línea del informe (AC-12 queda ampliado, no anulado)

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0013/AC-NN`. -->

## Contexto

`mth review record` toma el número de bloqueantes de la línea `BLOQUEANTES: <n>` que escribe el propio revisor (SPEC-0001/AC-12). Dos problemas:

1. **El número lo declara el modelo.** Un revisor que cuenta mal, o que declara `0` junto a un hallazgo `[bloqueante]`, abre el gate. El número que decide si una rama se integra debe salir de un cálculo de `mth`, no de lo que el modelo afirme.
2. **El gate depende de la suerte.** Si un informe con formato roto se resuelve relanzando agentes hasta que «sale bien», el resultado deja de ser una verificación. Además, lo que se guarda en `.work/reviews/` ha sido, a veces, un resumen escrito después, de modo que no se puede auditar qué dijo el revisor (PRINCIPLES §10 pide el registro sobre el commit exacto).

## Objetivo

1. El número de bloqueantes registrado es el que cuenta `mth` en la sección `HALLAZGOS` del informe. La línea `BLOQUEANTES: <n>` del agente es una declaración que se contrasta, no la fuente.
2. Una discrepancia, o un informe que `mth` no sabe leer, se registra como revisión **fallida**: estado seguro, no aprueba nada y deja rastro.
3. El informe literal de cada intento queda archivado con el SHA revisado y el número de intento, y el registro lleva su huella.
4. Los reintentos se cuentan en el registro, para poder ver si el fallo está en el prompt del revisor.

## Fuera de alcance

- Evaluar si los hallazgos son correctos o si la severidad está bien puesta: sigue siendo trabajo del revisor.
- Cambiar el formato de salida de los revisores: se endurece su lectura, no su contenido.
- Lanzar o relanzar revisores desde `mth`: lo hace la sesión principal (skill `mth-review`).

## Comportamiento

### Formato que `mth` sabe leer

El informe tiene una única sección `HALLAZGOS` (línea que es solo `HALLAZGOS`). Termina en la siguiente cabecera conocida (`FUERA DE ALCANCE`, `RESUMEN:`, `BLOQUEANTES:`, `TESTS:`, `CRITERIOS`, `ALCANCE:`). Dentro solo se admiten:

- una línea `ninguno` (con o sin punto final), y entonces no puede haber más hallazgos;
- líneas de hallazgo `N. [severidad] …` con severidad `bloqueante`, `importante` o `sugerencia` (sin distinguir mayúsculas);
- líneas de continuación, que empiezan por un espacio o tabulador;
- líneas en blanco.

Además, la marca `[bloqueante]` no puede aparecer en ningún otro sitio del informe (líneas sangradas, otras secciones, prosa): cada marca debe ser una línea de hallazgo contada. Cualquier otra cosa (viñetas, texto suelto, una severidad desconocida, dos secciones `HALLAZGOS`, ninguna) hace el informe **ilegible**. La última línea no vacía debe ser `BLOQUEANTES: <n>`.

### Cálculo

`blocking` es el número de líneas de hallazgo con severidad `bloqueante`. Se guardan también las cuentas de `importante` y `sugerencia`. Si `BLOQUEANTES: <n>` no coincide con `blocking`, la revisión es fallida. Un revisor que no pudo revisar y termina con `BLOQUEANTES: 1` sin hallazgo `[bloqueante]` también es una discrepancia: está bien que no pase.

### Registro

`mth review record <agente> --report <fichero> --summary "…"` escribe siempre una entrada en `reviews.json` para el HEAD y el agente:

| Campo | Contenido |
|---|---|
| `status` | `ok` o `failed` |
| `blocking` | bloqueantes calculados (`ok`) |
| `declared` | número de la última línea, si se pudo leer |
| `findings` | cuenta por severidad |
| `attempts` | intentos de registro de ese agente sobre ese SHA, fallidos y correctos |
| `previous_status` | estado de la entrada que sustituye, si había una |
| `failures` | fallos consecutivos; un registro `ok` lo pone a 0 |
| `reason` | causa del fallo, en una frase (`failed`) |
| `report` / `report_sha256` | ruta del archivo literal y su huella |

Un registro `ok` posterior sustituye al `failed` y conserva el contador `attempts`. Un commit nuevo cambia el SHA y el contador empieza de cero.

### Archivo literal

Antes de analizarlo, `mth` copia el informe, byte a byte, a `.work/reviews/<sha>-<agente>-<n>.md` (`<sha>` completo, `<n>` el número de intento). Nunca sobrescribe un archivo existente. Si `--report` ya apunta a esa ruta, no copia. Un resumen se guarda aparte y enlaza al original; no sustituye al informe.

### Reintentos

Ante un registro `failed`, la sesión principal pide **una** corrección al **mismo** agente con `SendMessage` (mismo contexto), nombrando el motivo que imprime `mth`, y registra de nuevo. No lanza otro agente desde cero. Si fallan dos intentos seguidos (`failures` ≥ 2), se detiene y avisa (PRINCIPLES §11): el fallo está en el prompt del revisor, y `attempts` y `reason` permiten verlo. `mth review status` muestra los intentos.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| El informe declara un número distinto del que cuenta `mth` | Comparación de `declared` y `blocking` | Registro `failed` con `reason`; error; la integración sigue bloqueada |
| Formato ilegible (sección ausente o repetida, líneas desconocidas, falta la última línea) | Lectura estricta | Registro `failed`; error con el motivo |
| Informe ausente, vacío o de más de 256 KiB | Lectura del fichero | Registro `failed` sin huella; error |
| Informe que no es UTF-8 | Decodificación | Se archiva tal cual (es la evidencia), con su huella; registro `failed`; error |
| No se puede archivar el informe (disco, permisos) | Error de escritura | No se registra nada y la revisión sigue pendiente; error reanudable |
| `.work/reviews` es un enlace simbólico que sale del repo, o el agente o el SHA llevan caracteres no seguros | Resolución de la ruta y validación del nombre | No se archiva ni se registra nada; error |
| El disco falla a mitad de la copia | `OSError` al escribir | Se borra el archivo parcial; no se registra nada |
| `--report` apunta fuera del repo (una clave, `~/.config`) o no es un fichero regular (FIFO, dispositivo) | Resolución de la ruta y `S_ISREG` | Fuera del repo: error sin leer ni registrar nada. No regular: registro `failed`. El motivo nunca cita contenido del informe, solo el número de línea |
| Dos `mth review record` a la vez | Bloqueo exclusivo (`flock`) sobre leer-modificar-escribir | Se serializan: no se pierde ninguna entrada ni se estropean los contadores. Sin `fcntl` (Windows) el registro es secuencial |
| Otro registro mantiene el bloqueo más de 30 s | `flock` no bloqueante con espera creciente y plazo | Error accionable; no se registra nada |
| `--summary` de más de 4 KiB | Tamaño | Error; no se registra nada |
| `reviews.json` corrupto | Lectura del registro | Error antes de archivar; no se registra nada |
| `reviews.json` es JSON válido pero la entrada del agente tiene otra forma (contadores no numéricos) | Validación de la entrada previa | Error de etapa `store` con la pista de borrarlo; no se registra nada |
| El sistema de ficheros no admite `flock` | `OSError` distinto de «ocupado» | Error inmediato de etapa `lock`, sin esperar 30 s |
| Falla la escritura del registro tras archivar | `atomic_write` | Error reanudable; queda un archivo huérfano y el siguiente intento salta su número |
| Informe repetido en el mismo intento (ruta de archivo ocupada) | El archivo existe | El número de intento sube hasta uno libre; nunca se sobrescribe |
| Segundo fallo seguido | `failures` ≥ 2 | El mensaje manda detenerse y avisar, no relanzar |
| `mth integrate` con un revisor `failed` | `review.check` | Rechaza con «revisión fallida» y el motivo, distinto de «falta» |

## Criterios de aceptación

- **AC-01**: `mth review record` registra como `blocking` el número de líneas `[bloqueante]` de `HALLAZGOS`, y `ninguno` cuenta 0.
- **AC-02**: Si `BLOQUEANTES: <n>` no coincide con la cuenta de `mth` (en cualquier sentido), la revisión queda registrada como `failed`, el comando termina con error y `mth integrate` no la acepta.
- **AC-03**: Un informe ilegible (sección `HALLAZGOS` ausente o repetida, línea no admitida, severidad desconocida, `ninguno` junto a hallazgos o sin la última línea) queda registrado como `failed`.
- **AC-04**: Un informe ausente, vacío o de más de 256 KiB queda registrado como `failed`.
- **AC-05**: El informe se archiva byte a byte en `.work/reviews/<sha>-<agente>-<n>.md` sin sobrescribir nunca; el registro guarda la ruta y el `sha256`.
- **AC-06**: `attempts` cuenta los intentos por agente y SHA, sobrevive a un registro correcto posterior y se reinicia con un SHA nuevo.
- **AC-07**: `mth review status` muestra una revisión `failed` con su motivo y los intentos, y `mth integrate` la rechaza distinguiéndola de una revisión pendiente.
- **AC-08**: Si no se puede archivar el informe, no se registra nada.
- **AC-10**: Una marca `[bloqueante]` fuera de las líneas de hallazgo contadas (sangrada, tras otra cabecera, en prosa) deja la revisión `failed`, aunque el informe declare 0.
- **AC-11**: Si `.work/reviews` resuelve fuera del repo, o el agente o el SHA no son nombres seguros, no se archiva ni se registra nada; si la copia falla a medias no queda un archivo parcial.
- **AC-12**: `--report` fuera del repo se rechaza sin registrar nada, un fichero no regular se registra como `failed`, falta de `--report` es un error claro y el motivo del fallo nunca cita el contenido del informe.
- **AC-13**: Registros simultáneos de agentes distintos no pierden ninguna entrada.
- **AC-14**: Un `reviews.json` corrupto, un bloqueo que no se obtiene a tiempo o un `--summary` de más de 4 KiB son errores que no registran nada, y el evento de traza `review.not_recorded` (y `review.failed`, con motivo y fallos, cuando se registra una revisión fallida) lleva la etapa (`rejected`, `archive`, `lock`, `store`) y la ruta de un archivo huérfano si lo hay.
- **AC-09**: Un registro `ok` tras un `failed` deja la revisión aprobada con los bloqueantes calculados.

## Notas

Límites aceptados: entre comprobar el enlace simbólico del archivo y abrirlo hay una ventana (TOCTOU) que exige escribir en el checkout local, y `xb` no sigue enlaces en el último componente; `check` no vuelve a verificar el `report_sha256` contra el archivo. Además, la cuenta solo detecta incoherencias. Un revisor que omite un hallazgo sigue produciendo un `ok`; que los hallazgos sean correctos y estén bien clasificados es juicio del revisor.


La skill `mth-review` y el README describen el flujo de reintento con `SendMessage`. Los registros existentes (sin `status`) se leen como `ok`.
