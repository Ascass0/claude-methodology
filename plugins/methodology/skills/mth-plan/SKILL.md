---
name: mth-plan
description: Crea y acuerda con la persona el plan de ejecución de una idea antes de crear su rama, su spec o su código. Úsala cuando la persona proponga una feature, un fix o un hotfix y no haya un plan acordado, y al reanudar una idea cuyo plan está en borrador.
---

# Plan acordado

`mth` es el comando del contexto de sesión (`$MTH`). Toda idea de tipo `feat`, `fix` o `hotfix` necesita un plan acordado con la persona **antes** de crear la rama, la spec o el código. El plan es un fichero local `.work/plans/PLAN-NNNN-<slug>.md` que nunca se commitea: los agentes trabajan contra él y no contra la memoria de la sesión. `chore` y `docs` no lo necesitan.

## Quién hace qué

| Quién | Qué |
|---|---|
| Tú (hilo principal) | Reúnes el contexto, lanzas al planificador, presentas el borrador, lo discutes con la persona y ejecutas `mth plan agree` solo con su visto bueno |
| `planificador` (agente del plugin, siempre Opus) | Redacta el plan con los agentes del catálogo, las oleadas, las dependencias y los agentes que conviene instalar. No puede preguntar: lo que no sabe queda como pregunta abierta |
| Persona | Decide y da el visto bueno |
| Orquestador | Después, instala los agentes del catálogo que el plan recomienda y reparte el trabajo apoyándose en el plan |

## Pasos

1. `mth plan list`. Si ya hay un plan acordado o en curso para esta idea, úsalo y salta al paso 8.
2. `mth plan new <slug> --title "<título>"` crea el plan en `borrador` con la plantilla. El slug: minúsculas, dígitos y guiones.
3. Lanza al planificador con la herramienta Agent: `subagent_type` `methodology:planificador` y **`model: "opus"` siempre** (no sale de `mth models` ni de la configuración). Encargo, autocontenido (no ve esta conversación):

   ```
   Plan para: <la idea en una frase>
   - Fichero de plan (plantilla de mth, vacío): <ruta del paso 2>
   - Lo que quiere la persona: <con sus palabras y el contexto>
   - Decisiones ya tomadas: <las que haya en la conversación, o «ninguna»>
   - Restricciones y cosas descartadas: <o «ninguna»>
   - Specs y ADR relacionados: <IDs, o «no sé»>
   - Modelo: opus
   - Principios: <ruta de PRINCIPLES.md del contexto de sesión>
   Devuelve solo el contenido completo del plan.
   ```

   No hace falta una discusión previa: si la hubo, inclúyela; si no, el planificador deja lo que falte como preguntas abiertas.
4. Guarda su respuesta **tal cual** en el fichero del plan. No la retoques para que `agree` pase.
5. Preséntalo a la persona: tareas por oleada con su agente sugerido, agentes a instalar y preguntas abiertas, con la ruta del fichero. Resuelve las preguntas abiertas con `AskUserQuestion`.
6. Itera: si la persona cambia algo, relanza al planificador (mismo encargo más «Correcciones de la persona: …» y el plan actual) y guarda el resultado. Un cambio trivial que la persona dicte lo puedes escribir tú en el fichero.
7. **Agentes a instalar:** si la sección no está vacía, pregunta a la persona si los aprueba. Los que rechace se quitan del plan (y la tarea que los usaba pasa a otro agente o al hilo principal). Los que apruebe los instala el orquestador (`mth agents add`, oleada 0) al empezar; sin orquestador, los instalas tú.
8. Con el visto bueno **explícito** de la persona: `mth plan agree PLAN-NNNN`. Valida el plan y, si falla, devuelve los problemas: corrígelos con la persona. Nunca edites el estado a mano.
9. Crea la rama con `mth branch <tipo> <slug> --plan PLAN-NNNN` y sigue la skill `mth-develop`. Al terminar el trabajo del plan: `mth plan done PLAN-NNNN` (o `--abandon`).

## Reglas

- Nada de rama, spec ni código antes del visto bueno de la persona.
- El planificador siempre con `model: "opus"`.
- El plan cita specs y ADR; ningún documento versionado ni `Refs:` de commit cita un `PLAN-NNNN`.
- El orquestador anota en el «Registro de ejecución» lo que se hizo y cada desviación con su motivo.
- Una hoja de ruta (varias fases) usa la sección `Fases`; cada fase tiene después su propio plan.
