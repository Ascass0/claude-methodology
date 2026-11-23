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

Cualquier otra cosa (viñetas, texto suelto, una severidad desconocida, dos secciones `HALLAZGOS`, ninguna) hace el informe **ilegible**. La última línea no vacía debe ser `BLOQUEANTES: <n>`.

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
| `reason` | causa del fallo, en una frase (`failed`) |
| `report` / `report_sha256` | ruta del archivo literal y su huella |

Un registro `ok` posterior sustituye al `failed` y conserva el contador `attempts`. Un commit nuevo cambia el SHA y el contador empieza de cero.

### Archivo literal

Antes de analizarlo, `mth` copia el informe, byte a byte, a `.work/reviews/<sha>-<agente>-<n>.md` (`<sha>` completo, `<n>` el número de intento). Nunca sobrescribe un archivo existente. Si `--report` ya apunta a esa ruta, no copia. Un resumen se guarda aparte y enlaza al original; no sustituye al informe.

### Reintentos

Ante un registro `failed`, la sesión principal pide **una** corrección al **mismo** agente con `SendMessage` (mismo contexto), nombrando el motivo que imprime `mth`, y registra de nuevo. No lanza otro agente desde cero. Si el segundo intento también falla, se detiene y avisa (PRINCIPLES §11): el fallo está en el prompt del revisor, y `attempts` y `reason` permiten verlo. `mth review status` muestra los intentos.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| El informe declara un número distinto del que cuenta `mth` | Comparación de `declared` y `blocking` | Registro `failed` con `reason`; error; la integración sigue bloqueada |
| Formato ilegible (sección ausente o repetida, líneas desconocidas, falta la última línea) | Lectura estricta | Registro `failed`; error con el motivo |
| Informe ausente, vacío, ilegible por codificación o de más de 256 KiB | Lectura del fichero | Registro `failed` sin huella; error |
| No se puede archivar el informe (disco, permisos) | Error de escritura | No se registra nada y la revisión sigue pendiente; error reanudable |
| Informe repetido en el mismo intento (ruta de archivo ocupada) | El archivo existe | El número de intento sube hasta uno libre; nunca se sobrescribe |
| Segundo intento fallido | `attempts` ≥ 2 con `failed` | El mensaje manda detenerse y avisar, no relanzar |
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
- **AC-09**: Un registro `ok` tras un `failed` deja la revisión aprobada con los bloqueantes calculados.

## Notas

La skill `mth-review` y el README describen el flujo de reintento con `SendMessage`. Los registros existentes (sin `status`) se leen como `ok`.
