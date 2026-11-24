# SPEC-0018 · Formato compacto de specs y ADR

- Estado: aprobada
- Fecha: 2026-11-24
- Formato: compacto
- ADRs: [ADR-0014](../adr/process/ADR-0014-formato-compacto-de-specs-y-adr.md)
- Sustituye a: —

## Contexto

- Lo que el plugin carga en cada sesión y los documentos del repo están en prosa para personas; los lee sobre todo un agente.
- [ADR-0014](../adr/process/ADR-0014-formato-compacto-de-specs-y-adr.md) fija el formato; esta spec lo implementa.

## Objetivo

1. Plantillas de spec y ADR en el formato compacto (ES y EN).
2. `mth trace` valida el formato en los documentos que lo declaran.
3. Baja el tamaño de lo que se carga en cada sesión, sin perder ninguna regla.

## Fuera de alcance

- Convertir specs y ADR existentes.
- El ADR de adopción que genera `mth init` (`adoption.py`): sigue en su formato.
- Comprobar la longitud con script.
- Cubrir cada `FM-NN` con un test (lo exige el ADR de los tests, posterior).

## Comportamiento

### Marca

- Línea de cabecera `- Formato: compacto` (`- Format: compact` con `language.docs = en`).
- Sin la marca, el documento no se valida con las reglas de esta spec.

### Specs compactas

- Cada `- **AC-NN**: …` sigue un patrón EARS en una sola línea; las palabras clave salen de `lang.py`:

  | Patrón | ES | EN |
  |---|---|---|
  | Disparador | `CUANDO …, … DEBE …` | `WHEN …, … SHALL/MUST …` |
  | Condición | `SI …, ENTONCES … DEBE …` | `IF …, THEN … SHALL/MUST …` |
  | Estado | `MIENTRAS …, … DEBE …` | `WHILE …, … SHALL/MUST …` |
  | Permanente | `… DEBE …` (sin palabra de apertura) | `… SHALL/MUST …` |

- La sección de modos de fallo es una tabla `| ID | Causa | Respuesta | Cubierto por |`; cada fila empieza por un `FM-NN`.
- Los `FM-NN` son únicos en la spec.
- Un `FM-NN` suelto referencia un modo de la misma spec; `SPEC-NNNN/FM-NN` referencia el de otra.

### ADR compactos

- Campos (encabezados de nivel 2): `Contexto`, `Decisión`, `Rechazado`, `Consecuencias`, `Impone` (EN: `Context`, `Decision`, `Rejected`, `Consequences`, `Imposes`).

### Referencias

- `SPEC-NNNN/FM-NN` se comprueba en todo fichero comprobado, también fuera de documentos compactos: la spec DEBE existir y definir ese `FM-NN`.

### Lo que se carga siempre

- `context/core.md`, `templates/claude-block.md`, `PRINCIPLES.md` y las descripciones de skills y agentes (`agents/` y plantillas del catálogo) se reescriben en el estilo de PRINCIPLES §7.
- Medida antes → después en el PR: tokens estimados como caracteres / 4 (sin tokenizador local; mismo método en las dos medidas).

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Documento sin marca | No se valida: conserva el comportamiento anterior | AC-02 |
| FM-02 | Patrón EARS rechaza un criterio válido | El mensaje muestra los patrones admitidos; el criterio se reescribe | AC-03 |
| FM-03 | `AC-NN` con `DEBE` en otra línea | Se rechaza: una regla por línea | AC-03 |
| FM-04 | Palabras clave de otro idioma | No se reconocen: solo valen las de `language.docs` | AC-07 |
| FM-05 | Referencia `SPEC-NNNN/FM-NN` a una spec inexistente o sin ese modo | Hallazgo que nombra la referencia | AC-06 |
| FM-06 | La reescritura pierde una regla | Test de conteo de palabras normativas y revisión | AC-09 |

## Criterios de aceptación

- **AC-01**: CUANDO `mth doc` crea una spec o un ADR (ES o EN), el documento DEBE llevar la marca de formato y DEBE pasar `mth trace` sin hallazgos.
- **AC-02**: MIENTRAS un documento no lleve la marca, `mth trace` NO DEBE aplicarle las reglas de EARS, de `FM-NN` ni de campos del ADR.
- **AC-03**: SI un `AC-NN` de una spec compacta no sigue ningún patrón EARS, ENTONCES `mth trace` DEBE reportarlo con su fichero y su línea.
- **AC-04**: SI un ADR compacto no tiene alguno de los cinco campos, ENTONCES `mth trace` DEBE reportar cada campo que falta.
- **AC-05**: SI una spec compacta repite un `FM-NN` o tiene una fila de modos de fallo sin ID, ENTONCES `mth trace` DEBE reportarlo con su línea.
- **AC-06**: SI un `FM-NN` suelto o un `SPEC-NNNN/FM-NN` apunta a un modo que no existe, ENTONCES `mth trace` DEBE reportarlo.
- **AC-07**: Las palabras clave EARS, los campos del ADR y la marca DEBEN salir del vocabulario de `language.docs`.
- **AC-08**: `core.md`, `claude-block.md`, `PRINCIPLES.md` y las descripciones de skills y agentes DEBEN pesar menos que antes de esta spec.
- **AC-09**: La reescritura DEBE conservar todas las palabras normativas de `PRINCIPLES.md` (DEBE, NO DEBE, DEBERÍA, PUEDE) y todos los puntos de las listas de reglas y de parada de `core.md`.
- **AC-10**: Los specs y ADR existentes DEBEN seguir pasando `mth trace` sin cambios.

## Notas

—
