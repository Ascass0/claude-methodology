# ADR-0018 · Actualización de claude-methodology

- Estado: aceptado
- Fecha: 2026-11-25
- Categoría: methodology
- Formato: compacto

## Contexto

- Se pone el repo al día con claude-methodology 0.14.0 con `mth update`.

## Decisión

1. Se aplican las brechas automáticas de esta ejecución (sin cambiar ningún valor ya decidido):
   - `config`: trace.legacy_base
   - `bloque`: bloque stale en CLAUDE.md
   - `hook`: hook commit-msg stale
2. Quedan pendientes; las conduce la skill `mth-update` o la persona:
   - `triangulacion` (informativa): 123 criterios con un único test

## Rechazado

- Cambiar valores ya decididos: es trabajo de `mth reconfigure`.
- Convertir documentos sin aprobación: es una migración que decide la persona.

## Consecuencias

- **+** `mth update --plan` lista lo que falta y queda en «al día» al terminar.
- **−** Lo pendiente exige trabajo aparte de esta rama.

## Impone

- [script] `mth update --plan`: lista las brechas con su clase.
