# ADR-0019 · Actualización de claude-methodology

- Estado: aceptado
- Fecha: 2026-11-26
- Categoría: methodology
- Formato: compacto

## Contexto

- Se pone el repo al día con claude-methodology 0.15.0 con `mth update`.
- Parte de las decisiones registradas en ADR-0018.

## Decisión

1. Se aplican las brechas automáticas de esta ejecución (sin cambiar ningún valor ya decidido):
   - `bloque`: bloque stale en CLAUDE.md
2. Quedan pendientes; las conduce la skill `mth-update` o la persona:
   - `humo` (informativa): Las restricciones de los agentes del catálogo no se han verificado con Claude Code 2.1.332 (Claude Code) (mth smoke).
   - `triangulacion` (informativa): 43 criterios con un único test

## Rechazado

- Cambiar valores ya decididos: es trabajo de `mth reconfigure`.
- Convertir documentos sin aprobación: es una migración que decide la persona.

## Consecuencias

- **+** `mth update --plan` lista lo que falta y queda en «al día» al terminar.
- **−** Lo pendiente exige trabajo aparte de esta rama.

## Impone

- [script] `mth update --plan`: lista las brechas con su clase.
