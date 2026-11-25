# ADR-0007 · Reestructuración reutilizando la entrevista de adopción

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process
- Formato: compacto

## Contexto

- La entrevista de adopción ([ADR-0003](ADR-0003-adopcion-guiada-por-perfiles-de-destino.md), [SPEC-0004](../../features/SPEC-0004-adopcion-guiada.md)) solo funciona una vez: `mth survey` y `mth init` se niegan a actuar en un repo adoptado.
- Cambiar después una decisión (autonomía, revisores, rutas de specs, hooks) obliga a editar `.claude/methodology.toml` a mano: se pierden las explicaciones de cada opción y el registro del porqué.
- El ADR de adopción dice que cambiar una decisión exige un ADR nuevo.

## Decisión

1. La reestructuración DEBE reutilizar el catálogo de preguntas, el formato de respuestas y el traductor de respuestas a configuración de la adopción. NO DEBE haber un segundo catálogo.
2. `mth survey --reconfigure` DEBE inventariar un repo adoptado y ofrecer todas las preguntas aplicables con el valor actual; `--only` limita a preguntas o bloques (`flujo`, `documentacion`, `calidad`, `agente`).
3. `mth reconfigure --answers` DEBE aplicar las respuestas **sobre la configuración actual** (no sobre la plantilla), conservar lo que no se pregunta, validar todo antes de tocar nada y abrir `chore/reconfigure-methodology` con la configuración nueva y un ADR de reestructuración en un único commit.
4. La skill `mth-reconfigure` (Opus) conduce la conversación: formulario completo, bloques o un cambio descrito con palabras de la persona. Las migraciones que piden las respuestas (convertir specs, renombrar agentes, crear CI) se hacen en la misma rama tras aprobar el plan.
5. El ADR de reestructuración NO DEBE editar los anteriores: cita el último ADR de adopción o reestructuración y lista qué claves pasan de qué valor a cuál.

## Rechazado

- `mth init` sobre un repo adoptado: mezcla operaciones con precondiciones opuestas y partiría de la plantilla, perdiendo la configuración propia.
- Editar a mano con la skill como guía: sin validación determinista ni ADR generado, que es lo que la adopción garantiza.
- Catálogo de preguntas propio: duplica textos y mantenimiento.

## Consecuencias

- **+** Cualquier decisión de la adopción se revisa con la misma explicación y rigor, y queda en un ADR.
- **−** La configuración se regenera: se pierden sus comentarios; el ADR conserva el porqué.
- **riesgo** Cambiar la rama de integración o las rutas de specs afecta a las ramas abiertas → la skill lo advierte antes de aplicar y lo incluye en el plan de migración.

## Impone

- [script] `mthlib/adoption.py` y `mthlib/survey.py` (`mth survey --reconfigure`, `mth reconfigure --answers`).
- [criterio] Skill `mth-reconfigure`: plan de migración aprobado antes de aplicar.
