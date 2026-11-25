# SPEC-0013 · Registro de revisiones calculado por mth

- Estado: implementada
- Fecha: 2026-11-23
- Formato: compacto
- ADRs: [ADR-0008](../adr/process/ADR-0008-catalogo-de-plantillas-de-agentes.md)
- Sustituye a: la parte de [SPEC-0001](SPEC-0001-delegacion-verificable.md) que toma los bloqueantes de la última línea del informe (AC-12 queda ampliado, no anulado)


## Contexto

- `mth review record` toma el número de bloqueantes de la línea `BLOQUEANTES: <n>` que escribe el propio revisor (SPEC-0001/AC-12).
- **El número lo declara el modelo.** Un revisor que cuenta mal, o declara `0` junto a un hallazgo `[bloqueante]`, abre el gate: el número que decide la integración debe salir de un cálculo de `mth`.
- **El gate depende de la suerte.** Relanzar agentes hasta que el formato «salga bien» deja de ser verificación.
- Lo guardado en `.work/reviews/` a veces era un resumen posterior: no se puede auditar qué dijo el revisor (PRINCIPLES §10 pide el registro sobre el commit exacto).
- Decisión: [ADR-0009](../adr/process/ADR-0009-el-numero-de-bloqueantes-lo-calcula-mth.md).

## Objetivo

1. El número de bloqueantes registrado es el que cuenta `mth` en la sección `HALLAZGOS`; la línea `BLOQUEANTES: <n>` del agente se contrasta, no es la fuente.
2. Una discrepancia, o un informe ilegible, se registra como revisión **fallida**: estado seguro, no aprueba y deja rastro.
3. El informe literal de cada intento queda archivado con el SHA revisado y el número de intento, y el registro lleva su huella.
4. Los reintentos se cuentan, para ver si el fallo está en el prompt del revisor.

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

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | El informe declara un número distinto del que cuenta `mth` | Registro `failed` con `reason`; error; la integración sigue bloqueada | AC-02 |
| FM-02 | Formato ilegible (sección ausente o repetida, líneas desconocidas, falta la última línea) | Registro `failed`; error con el motivo | AC-03 |
| FM-03 | Informe ausente, vacío o de más de 256 KiB | Registro `failed` sin huella; error | AC-04 |
| FM-04 | Informe que no es UTF-8 | Se archiva tal cual (es la evidencia) con su huella; registro `failed`; error | AC-05 |
| FM-05 | No se puede archivar el informe (disco, permisos) | No se registra nada y la revisión sigue pendiente; error reanudable | AC-08 |
| FM-06 | `.work/reviews` es un enlace que sale del repo, o el agente o el SHA llevan caracteres no seguros | No se archiva ni registra nada; error | AC-11 |
| FM-07 | El disco falla a mitad de la copia | Se borra el archivo parcial; no se registra nada | AC-11 |
| FM-08 | `--report` fuera de `.work/` (clave, `~/.config`, `.env`) o no regular (FIFO, dispositivo) | Fuera del repo: error sin leer ni registrar nada. No regular: registro `failed`. El motivo nunca cita contenido del informe | AC-12 |
| FM-09 | Dos `mth review record` a la vez | Bloqueo exclusivo (`flock`): se serializan sin perder entradas ni estropear contadores; sin `fcntl` (Windows) el registro es secuencial | AC-13 |
| FM-10 | Otro registro mantiene el bloqueo más de 30 s | `flock` no bloqueante con espera creciente y plazo: error accionable; no se registra nada | AC-14 |
| FM-11 | `--summary` de más de 4 KiB | Error; no se registra nada | AC-14 |
| FM-12 | `reviews.json` corrupto | Error antes de archivar; no se registra nada | AC-14 |
| FM-13 | `reviews.json` válido pero con la entrada del agente de otra forma (contadores no numéricos) | Error de etapa `store` con la pista de borrarlo; no se registra nada | AC-14 |
| FM-14 | El sistema de ficheros no admite `flock` | Error inmediato de etapa `lock`, sin esperar 30 s | AC-14 |
| FM-15 | Falla la escritura del registro tras archivar | `atomic_write`: error reanudable; queda un archivo huérfano y el siguiente intento salta su número | AC-14 |
| FM-16 | Informe repetido en el mismo intento (ruta ocupada) | El número de intento sube hasta uno libre; nunca se sobrescribe | AC-05 |
| FM-17 | Segundo fallo seguido (`failures` ≥ 2) | El mensaje manda detenerse y avisar, no relanzar | AC-07 |
| FM-18 | `mth integrate` con un revisor `failed` | `review.check` rechaza con «revisión fallida» y el motivo, distinto de «falta» | AC-07 |

## Criterios de aceptación

- **AC-01**: CUANDO se ejecuta `mth review record`, `mth` DEBE registrar como `blocking` el número de líneas `[bloqueante]` de `HALLAZGOS`, y `ninguno` DEBE contar 0.
- **AC-02**: SI `BLOQUEANTES: <n>` no coincide con la cuenta de `mth` (en cualquier sentido), ENTONCES la revisión DEBE quedar registrada como `failed`, el comando DEBE terminar con error y `mth integrate` NO DEBE aceptarla.
- **AC-03**: SI el informe es ilegible (sección `HALLAZGOS` ausente o repetida, línea no admitida, severidad desconocida, `ninguno` junto a hallazgos o sin la última línea), ENTONCES DEBE quedar registrado como `failed`.
- **AC-04**: SI el informe está ausente, vacío o supera 256 KiB, ENTONCES DEBE quedar registrado como `failed`.
- **AC-05**: CUANDO se registra un informe, `mth` DEBE archivarlo byte a byte en `.work/reviews/<sha>-<agente>-<n>.md` sin sobrescribir nunca y guardar en el registro la ruta y el `sha256`.
- **AC-06**: `mth` DEBE contar en `attempts` los intentos por agente y SHA; el contador DEBE sobrevivir a un registro correcto posterior y reiniciarse con un SHA nuevo.
- **AC-07**: CUANDO se ejecuta `mth review status` o `mth integrate` y hay una revisión `failed`, `mth` DEBE mostrarla con su motivo y los intentos y rechazarla distinguiéndola de una pendiente.
- **AC-08**: SI no se puede archivar el informe, ENTONCES `mth` NO DEBE registrar nada.
- **AC-09**: CUANDO se registra un `ok` tras un `failed`, `mth` DEBE dejar la revisión aprobada con los bloqueantes calculados.
- **AC-10**: SI aparece una marca `[bloqueante]` fuera de las líneas de hallazgo contadas (sangrada, tras otra cabecera, en prosa), ENTONCES la revisión DEBE quedar `failed` aunque el informe declare 0.
- **AC-11**: SI `.work/reviews` resuelve fuera del repo o el agente o el SHA no son nombres seguros, ENTONCES `mth` NO DEBE archivar ni registrar nada; SI la copia falla a medias, ENTONCES NO DEBE quedar un archivo parcial.
- **AC-12**: SI `--report` apunta fuera de `.work/`, ENTONCES `mth` DEBE rechazarlo sin registrar nada; SI no es un fichero regular, ENTONCES DEBE registrar `failed`; SI falta `--report`, ENTONCES DEBE dar un error claro; el motivo del fallo NO DEBE citar el contenido del informe.
- **AC-13**: CUANDO se registran revisiones de agentes distintos a la vez, `mth` NO DEBE perder ninguna entrada.
- **AC-14**: SI `reviews.json` está corrupto, un bloqueo no se obtiene a tiempo o `--summary` supera 4 KiB, ENTONCES `mth` DEBE fallar sin registrar nada, y el evento de traza `review.not_recorded` (y `review.failed`, con motivo y fallos, al registrar una revisión fallida) DEBE llevar la etapa (`rejected`, `archive`, `lock`, `store`) y la ruta de un archivo huérfano si lo hay.

## Notas

Límites aceptados: entre comprobar el enlace simbólico del archivo y abrirlo hay una ventana (TOCTOU) que exige escribir en el checkout local, y `xb` no sigue enlaces en el último componente; `check` no vuelve a verificar el `report_sha256` contra el archivo. Además, la cuenta solo detecta incoherencias. Un revisor que omite un hallazgo sigue produciendo un `ok`; que los hallazgos sean correctos y estén bien clasificados es juicio del revisor.


La skill `mth-review` y el README describen el flujo de reintento con `SendMessage`. Los registros existentes (sin `status`) se leen como `ok`.
