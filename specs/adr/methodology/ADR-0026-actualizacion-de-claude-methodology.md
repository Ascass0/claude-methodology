# ADR-0026 · Actualización de claude-methodology

- Estado: aceptado
- Fecha: 2026-11-27
- Categoría: methodology
- Formato: compacto

## Contexto

- Se pone el repo al día con claude-methodology 0.18.0 con `mth update`.
- Parte de las decisiones registradas en ADR-0019.

## Decisión

1. Se aplican las brechas automáticas de esta ejecución (sin cambiar ningún valor ya decidido):
   - `config`: roles.planner, plans, secrets, audit, hooks.pre_commit
   - `agentes-desactualizados`: revisor-seguridad
2. Quedan pendientes; las conduce la skill `mth-update` o la persona:
   - `secretos` (decision): secrets.mode sin decidir: no se buscan secretos al integrar
   - `secretos-hook` (decision): secrets.hook sin decidir: no se escanea lo preparado antes de cada commit
   - `secretos-ci` (decision): secrets.ci sin decidir: la CI no escanea secretos en cada PR
   - `triangulacion` (informativa): 97 criterios con un único test

## Rechazado

- Cambiar valores ya decididos: es trabajo de `mth reconfigure`.
- Convertir documentos sin aprobación: es una migración que decide la persona.

## Consecuencias

- **+** `mth update --plan` lista lo que falta y queda en «al día» al terminar.
- **−** Lo pendiente exige trabajo aparte de esta rama.

## Impone

- [script] `mth update --plan`: lista las brechas con su clase.
