---
name: mth-develop
description: Ciclo autónomo de desarrollo dirigido por specs, de la spec a la versión publicada. Úsala siempre al empezar trabajo de desarrollo en un repo con .claude/methodology.toml (feature, bug, mantenimiento, tarea a medias) y cuando dudes del siguiente paso.
---

# Ciclo de desarrollo

`mth` es el comando que aparece en el contexto de sesión (`sh …/scripts/mth`), también disponible como `$MTH`. Trabajas sin pedir permiso, salvo los pasos que `autonomy.level` reserva a la persona: el guard te pide su confirmación y, si la rechaza, no lo reintentas por otra vía. Ejecuta `mth status` si no sabes en qué punto estás.

## 1. Clasifica el cambio (PRINCIPLES §12)

| Tipo | Rama | Spec | Fragmento | Revisión |
|---|---|---|---|---|
| Mantenimiento (docs, CI, deps sin cambio de comportamiento) | `chore/` | no | no | no |
| Bug | `fix/` | referencia la spec o el issue afectado | sí | sí |
| Comportamiento nuevo | `feat/` | **obligatoria** (se escribe en la rama) | sí | sí |
| Estructural | `feat/` o `chore/` | sí + **ADR aceptado antes de implementar** | sí | sí |
| Bug en producción (main) | `hotfix/` | referencia | sí (patch) | sí |

## 2. Plan acordado → skill `mth-plan`

Para `feat`, `fix` y `hotfix` (`plans.required_for`), antes de crear la rama: `mth plan new`, el agente `planificador` redacta el borrador, la persona lo discute y da su visto bueno y `mth plan agree PLAN-NNNN` lo fija. El plan es un fichero local de `.work/plans/` (nunca se commitea) y no lo cita ningún documento versionado. `chore` y `docs` no lo necesitan. Al terminar el trabajo: `mth plan done PLAN-NNNN`.

## 3. Rama → skill `mth-branch`

`mth branch feat <slug> --plan PLAN-NNNN` (añade `--spec SPEC-NNNN` si la spec ya existe). Para trabajo separable dentro de la feature, ramas hijas (`--child`), solo si se justifica.

## 4. Spec y decisiones → skill `mth-spec`

Antes de planificar una feature o un cambio estructural, si el repo tiene instalado el agente `explorador-specs` (catálogo del plugin, `mth agents list`), pídele qué specs, criterios, modos de fallo y ADR aplican a la tarea y qué falta por decidir: devuelve IDs y rutas, no el contenido.

Si la spec no existe, escríbela en la propia rama como primer commit: contexto, objetivo, fuera de alcance, comportamiento, **modos de fallo** y **criterios de aceptación verificables**. Pásala a `aprobada` cuando sea coherente con los principios y los ADR vigentes. Toda decisión estructural va en un ADR aceptado antes de implementarla. `mth integrate` rechaza una feature cuyo fragmento no referencie su spec.

## 5. Implementa (orquestas, los agentes `dev-*` implementan)

Tú mantienes la spec, el plan acordado y las decisiones; el reparto parte del plan acordado y las desviaciones se anotan en su «Registro de ejecución». La implementación especializada la delegas en los agentes `dev-*` del repo (`.claude/agents/`) cuyo ámbito cubra la tarea; su `description` dice cuál. Si ninguno encaja, implementas tú.

Delegar tiene un coste de coordinación: si el trabajo es pequeño, implementa tú. Si delegas dos o más tareas, el reparto va en la spec:

1. **Plan:** sección `## Plan de trabajo` de la spec (formato en la skill `mth-spec`). Cada tarea tiene sus ficheros permitidos y sus criterios. Las tareas de una misma oleada no comparten ficheros y no deben dejarte ninguna decisión de diseño. Lo que dependa de otra tarea va en la oleada siguiente. `mth plan check SPEC-NNNN` sin errores antes de lanzar nada; el plan se commitea con la spec.
2. **Modelo** de cada tarea: `mth plan model SPEC-NNNN T-NN` imprime el alias (`haiku`, `sonnet`, `opus`) que pasas como `model` a la herramienta Agent. Lo fija la columna `Modelo` del plan o, si está vacía, `models.task` (`mth models` muestra la configuración).
3. **Encargo** a cada agente de la oleada, en paralelo y autocontenido (no ve esta conversación):

   ```
   Encargo para <dev-agente>
   - Rama: <rama> (base <destino>). Tarea: <T-NN> de <SPEC-NNNN>
   - Spec: <ruta y sección>. Criterios de esta tarea: <AC-NN>
   - Modos de fallo a cubrir: <de la spec>
   - Ficheros permitidos (solo estos): <de la fila del plan>
   - Restricciones: <ADR, flags, convenciones>. Principios: <ruta de PRINCIPLES.md>
   - Hecho cuando: <tests concretos pasan>
   - No hagas commits ni toques git. Si necesitas decidir algo que la spec no fija, no lo decidas: status "blocked" y la pregunta en "questions".
   - Termina devolviendo SOLO este JSON (todos los campos, ninguno más):
     {"task": "<T-NN>", "status": "done | blocked | failed",
      "files": ["<ficheros creados, modificados o borrados>"], "criteria": ["<AC-NN cubiertos>"],
      "tests": [{"name": "<test>", "result": "pass | fail"}],
      "decisions": [], "deviations": [], "questions": []}
   ```
4. **Manifiestos:** guarda la respuesta JSON de cada agente tal cual en `.work/plans/` (local, excluido de git). Nunca la edites para que pase.
5. **Verificación de la oleada**, con sus cambios sin confirmar: `mth plan verify SPEC-NNNN --wave N --manifest <f1> --manifest <f2> … [--model T-NN=<alias> …]`. Pasa `--model` para cada tarea que no se ejecutó con su nivel planificado (por ejemplo, un reintento): así las métricas atribuyen bien cada intento. Comprueba que cada tarea terminó, cubrió sus criterios con tests en verde, no salió de sus ficheros y que no hay cambios sin dueño ni afirmaciones falsas. Revisa además el diff real (`git diff`).
   - **No ejecutada / no completada** (agente caído, fuera de tiempo, manifiesto inválido, `blocked` o `failed`): relánzala **una sola vez**, con el modelo de `mth plan model SPEC-NNNN T-NN --retry` (un nivel más en `models.ladder`). Si vuelve a fallar, impleméntala tú o rehaz el plan (corrige la spec en un commit), y anótalo en el PR.
   - **Desvíos** (⚠): resuélvelos antes de confirmar, corrigiendo la spec si procede.
6. **Commits temáticos** tú (skill `mth-commit`) al cerrar cada oleada; la siguiente oleada empieza con el árbol limpio. Los agentes nunca hacen commits ni tocan git.

`mth plan stats` resume, por modelo, cuántos intentos terminan en `ok`. Úsalo al planificar: si un nivel falla a menudo en un tipo de tarea, súbelo en el plan; si acierta siempre, prueba uno menor.

Principios activos en todo momento: Design for Failure, fail-safe/fail-fast, parsimonia, excepciones solo donde se actúa, trazas con ID de correlación, docstrings mínimos, referencias `ADR-NNNN` en decisiones no obvias.

- Tests: uno por AC (con `verifies: SPEC-NNNN/AC-NN`), uno por modo de fallo, uno de regresión por bug. Ninguno más.
- **Fallo de causa desconocida** (un test, un comando o un comportamiento falla y no sabes por qué): si el repo tiene el agente `diagnosticador`, encárgale reproducirlo. Trabaja en un worktree aislado y devuelve la causa, la evidencia, un test de regresión y el fix propuesto como diff; el fix lo aplicas tú. Los trabajadores del catálogo usan el modelo `models.task`.
- Docs actualizadas en la misma rama.
- Commits temáticos durante el trabajo → skill `mth-commit`.

## 5b. Tests: triangulación y etiqueta (PRINCIPLES §6)

Ciclo por cada AC con entrada variable, tú o el agente `dev-*`:

1. Primer ejemplo en rojo.
2. Verde mínimo.
3. Segundo ejemplo de **otra clase de equivalencia** (otro límite, otro tipo de entrada): si el verde era una solución fija, vuelve a rojo.
4. Generaliza.
5. Refactoriza.
6. Elimina el andamiaje: tests de la misma clase para el mismo AC o que no aportan clase, límite ni modo de fallo propio.

Se impone el estado final, no el orden. Un AC sin entrada variable (`SI falta X, ENTONCES falla`) necesita un solo test.

Cada test lleva una etiqueta en su comentario: `verifies: SPEC-NNNN/AC-NN` o `/FM-NN`, `regression: <referencia>` (bug corregido, falla sin el fix) o `unit: <símbolo público>`. Sin etiqueta `mth trace` falla y `mth integrate` no avanza. `mth trace --single` lista los AC con un único test para que valores si triangular.

## 6. Cierra la rama

1. **Documentación:** delega en el agente de `roles.documenter` (por defecto `documentador`, incluido en el plugin), con el modelo `models.documenter`, con la rama, el comando del diff y las specs afectadas. Actualiza docs, fragmento de changelog y los registros documentales que exija el repo. Revisa sus cambios y haz el commit `docs`.
2. Feature: pon la spec en `implementada` solo si todos sus criterios están implementados y probados.
3. `mth trace` sin hallazgos → skill `mth-trace`.
4. `mth sync` para traer la rama destino.
5. Revisión → skill `mth-review` (sobre el HEAD final; el `verificador` va primero).
6. Integración → skill `mth-integrate`. Si la rama cambia `.claude/` (hooks, agentes, ajustes), es normal que el modo automático de Claude Code no te deje integrar cambios sobre tus propias salvaguardas: deja la rama lista y pide a la persona que ejecute `mth integrate`.

## 7. Versión → skill `mth-release`

Tras integrar en `development`, decide si publicar y con qué nivel con `mth release --plan` (solo lee; lo calcula `mth`, no tú): `publicar` → `mth release`; `esperar` → sigues con el trabajo abierto y vuelves a decidir al integrarlo; `no publicar` → el mantenimiento sin fragmento no versiona; `bloqueado` → corriges el nivel del fragmento, o avisas a la persona si es `1.0.0`. El detalle está en la skill `mth-release`.

Cuando `development` reúne features completas y estables entre sí, publica. Los hotfix se cierran con `mth hotfix finish`.

## Cuándo parar (PRINCIPLES §11)

Solo si dos specs o principios se contradicen sin que la precedencia lo resuelva, si un gate falla tres veces por la misma causa, o si la tarea exige algo irreversible fuera de las specs. En cualquier otro caso: elige la opción más conservadora, documéntala y continúa.
