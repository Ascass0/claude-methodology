# ADR-0007 · Reestructuración reutilizando la entrevista de adopción

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

La entrevista de adopción ([ADR-0003](ADR-0003-adopcion-guiada-por-perfiles-de-destino.md), [SPEC-0004](../../features/SPEC-0004-adopcion-guiada.md)) solo funciona una vez: `mth survey` y `mth init` se niegan a actuar en un repo ya adoptado. Después, cambiar una decisión (la autonomía, los revisores, dónde viven las specs, cómo se trata un hook) obliga a editar `.claude/methodology.toml` a mano. Así se pierden las explicaciones de cada opción y el registro de por qué se cambió, y el ADR de adopción dice que cambiar una decisión exige un ADR nuevo.

## Decisión

1. La reestructuración reutiliza el catálogo de preguntas, el formato de respuestas y el traductor de respuestas a configuración de la adopción. No hay un segundo catálogo.
2. `mth survey --reconfigure` inventaría un repo adoptado y ofrece todas las preguntas aplicables, con el valor actual de cada una. `--only` limita el formulario a preguntas o a bloques temáticos (`flujo`, `documentacion`, `calidad`, `agente`).
3. `mth reconfigure --answers` aplica las respuestas **sobre la configuración actual**, no sobre la plantilla, así que conserva todo lo que no se pregunta. Abre `chore/reconfigure-methodology` con la configuración nueva y un ADR de reestructuración en un único commit. Valida todo antes de tocar nada.
4. La skill `mth-reconfigure` (Opus) conduce la conversación: formulario completo, bloques elegidos o un cambio descrito con palabras de la persona. Igual que en la adopción, las migraciones que piden las respuestas (convertir specs, renombrar agentes, crear la CI) se hacen en la misma rama, después de que la persona apruebe el plan.
5. El ADR de reestructuración no edita los anteriores: cita el último ADR de adopción o de reestructuración y lista qué decisiones cambian y qué claves pasan de qué valor a cuál.

## Alternativas consideradas

- **Permitir `mth init` sobre un repo adoptado:** mezcla dos operaciones con precondiciones opuestas (repo sin adoptar frente a repo adoptado) y partiría de la plantilla, así que perdería la configuración propia.
- **Editar la configuración a mano con la skill como guía:** sin validación determinista de las respuestas ni ADR generado, que es justo lo que la adopción garantiza.
- **Un catálogo de preguntas propio de la reestructuración:** duplica los textos y su mantenimiento.

## Consecuencias

- **Positivas:** cualquier decisión de la adopción se puede revisar con la misma explicación y el mismo rigor, y queda registrada en un ADR.
- **Negativas:** el fichero de configuración se regenera, así que se pierden sus comentarios. El ADR conserva el porqué de cada cambio.
- **Riesgo aceptado:** cambiar la rama de integración o las rutas de specs en mitad de la vida del repo afecta a las ramas abiertas. La skill lo advierte antes de aplicar y lo incluye en el plan de migración.
