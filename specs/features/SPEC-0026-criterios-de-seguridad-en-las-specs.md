# SPEC-0026 · Criterios de seguridad en las specs

- Estado: implementada
- Fecha: 2026-11-27
- Formato: compacto
- ADRs: [ADR-0014](../adr/process/ADR-0014-formato-compacto-de-specs-y-adr.md)
- Sustituye a: —
- Seguridad: ninguna

## Contexto

- La seguridad solo se mira hoy en el diff (`revisor-seguridad`), cuando el diseño ya está escrito.
- La fase 3 de la hoja de ruta de seguridad mueve la pregunta a la spec: antes de escribir código se declara si la feature toca entrada externa, autenticación o datos sensibles.

## Objetivo

1. Una spec compacta puede declarar su superficie de seguridad en la cabecera.
2. Si la declara distinta de `ninguna`, lleva al menos un criterio `[SEG]` con test.
3. `revisor-seguridad` contrasta la declaración con el diff.

## Fuera de alcance

- Obligar a declarar la cabecera en specs existentes o clasificar la superficie automáticamente.
- El auditor de hardening (fase 4).

## Comportamiento

| Elemento | Regla |
|---|---|
| Cabecera | `- Seguridad: ninguna` o lista separada por comas (`entrada externa`, `autenticación`, `datos sensibles`). En inglés `- Security: none`. Opcional |
| Criterio de seguridad | AC normal (EARS) con la etiqueta `[SEG]` tras el ID: `- **AC-NN** [SEG]: …` (`[SEC]` en inglés) |
| `mth trace` | Cabecera con superficie ≠ `ninguna` y sin AC `[SEG]` = error. Sin cabecera, nada que validar |
| Plantillas | Spec nueva lleva `- Seguridad: ninguna` y un comentario guía |
| `revisor-seguridad` | Contrasta superficie declarada y diff; comprueba que cada `[SEG]` tiene test |

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Cabecera declara superficie y no hay `[SEG]` | `mth trace` falla y nombra la spec | AC-02 |
| FM-02 | Cabecera vacía o con texto no reconocible | Se trata como superficie declarada (exige `[SEG]`) | AC-03 |
| FM-03 | Etiqueta en una línea que no es un AC | No cuenta como criterio | AC-04 |

## Criterios de aceptación

- **AC-01**: CUANDO una spec compacta declara `- Seguridad: ninguna`, `mth trace` NO DEBE exigir criterios `[SEG]`.
- **AC-02**: SI una spec compacta declara una superficie distinta de `ninguna` y no tiene ningún AC `[SEG]`, ENTONCES `mth trace` DEBE reportar un error en la línea de la cabecera.
- **AC-03**: SI la cabecera de seguridad está vacía, ENTONCES `mth trace` DEBE tratarla como superficie declarada y exigir un AC `[SEG]`.
- **AC-04**: `mth trace` DEBE contar como criterio de seguridad solo las líneas `**AC-NN** [SEG]:` con formato EARS válido.
- **AC-05**: CUANDO una spec compacta no tiene cabecera de seguridad, `mth trace` NO DEBE reportar nada sobre seguridad.
- **AC-06**: Las plantillas de spec en español e inglés DEBEN llevar la cabecera de seguridad con valor `ninguna`/`none`.
- **AC-07**: La skill `mth-spec` y `revisor-seguridad` DEBEN documentar la cabecera y la etiqueta.

## Notas

- `[SEG]` sin test lo detecta ya la cobertura de AC de `mth trace`.
