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
   - `hook`: hook pre-commit absent
   - `secretos-workflow`: workflow de secretos absent
2. Decide la persona (skill `mth-update`):
   - `secretos`: `secrets.mode = "block"`: `mth integrate` bloquea si gitleaks encuentra secretos en la rama.
   - `secretos-hook`: `secrets.hook = "on"`: el hook `pre-commit` escanea lo preparado (`hooks.pre_commit = "own"`, sin hook ajeno).
   - `secretos-ci`: `secrets.ci = "on"`: workflow de secretos en cada PR; la protección de rama debe exigir su comprobación.
3. Queda pendiente:
   - `triangulacion` (informativa): 97 criterios con un único test.

## Rechazado

- Cambiar valores ya decididos: es trabajo de `mth reconfigure`.
- Convertir documentos sin aprobación: es una migración que decide la persona.

## Consecuencias

- **+** `mth update --plan` lista lo que falta y queda en «al día» al terminar.
- **−** Lo pendiente exige trabajo aparte de esta rama.
- **−** Integrar y commitear exige gitleaks (≥ 8.19.0) instalado (`mth tools install gitleaks`).

## Impone

- [script] `mth update --plan`: lista las brechas con su clase.
