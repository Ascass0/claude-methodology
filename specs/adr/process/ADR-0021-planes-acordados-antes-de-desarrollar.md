# ADR-0021 · Planes acordados antes de desarrollar

- Estado: aceptado
- Fecha: 2026-11-26
- Categoría: process
- Formato: compacto

## Contexto

- El ciclo de desarrollo no tiene un paso de plan discutido con la persona: la única noción de «plan» es la sección `## Plan de trabajo` de una spec, que reparte tareas entre agentes `dev-*` ([ADR-0001](ADR-0001-plan-y-manifiesto-verificados.md)).
- Una feature entera (SPEC-0022) se desarrolló sin plan acordado y los agentes dependían de la memoria de la sesión.
- Los artefactos de la sesión local viven en `.work/` y nunca se commitean ([ADR-0006](ADR-0006-directorio-de-trabajo-local-excluido-de-git.md)).
- Un subagente no puede preguntar a la persona: la conversación solo la tiene el hilo principal.
- El plan debe existir antes de la spec; un repo despliega los agentes del catálogo poco a poco, así que el plan no puede suponerlos instalados.
- [ADR-0002](ADR-0002-niveles-de-modelo.md) prohíbe fijar el modelo en la cabecera de los agentes del plugin; [ADR-0008](ADR-0008-catalogo-de-plantillas-de-agentes.md) deja solo `verificador` y `documentador` en `agents/`.

## Decisión

1. Toda idea de tipo `feat`, `fix` o `hotfix` DEBE tener un plan acordado antes de crear su rama. El plan es un fichero `.work/plans/PLAN-NNNN-<slug>.md`, local y nunca commiteado. Es anterior a la spec y distinto del «Plan de trabajo» de una spec, que sigue rigiéndose por ADR-0001. [script: `mth branch`, `mth integrate`]
2. Estados: `borrador`, `acordado`, `en curso`, `ejecutado`, `abandonado`. Solo `mth plan agree` pasa a `acordado`, y solo con la petición explícita de la persona. `mth plan agree` valida el plan: secciones obligatorias, tareas con dependencias sin ciclos, oleadas coherentes, ficheros disjuntos en una oleada y sin preguntas abiertas. [script: `mthlib/plans.py`]
3. Gate: `mth branch` exige `--plan PLAN-NNNN` acordado y `mth integrate` y `mth hotfix finish` comprueban que la rama tiene plan, para los tipos de `plans.required_for` (por defecto `feat`, `fix`, `hotfix`). `chore` y `docs` quedan exentos. El gate falla cerrado y no depende de `autonomy.level`. [script]
4. La cabecera del plan lista las ramas con `- Rama:`; `mth branch --plan` la añade y pasa el plan a `en curso`. Las ramas hijas heredan el plan de su rama de primer nivel.
5. Los IDs `PLAN-NNNN` no se citan en `Refs:` de los commits ni en documentos versionados: son locales y `mth` no puede validarlos. El plan cita las specs, no al revés.
6. `mth plan` se extiende con `new`, `agree`, `list`, `show` y `done`; sus acciones actuales (`check`, `verify`, `model`, `stats`) no cambian.
7. `planificador` es un agente del plugin en `agents/`, enlazado por `[roles].planner`: matiza ADR-0008, que lo limitaba a `verificador` y `documentador`. Es de solo lectura (lo exige su texto, como `verificador`), lee el catálogo con `mth agents list`, asigna solo agentes del catálogo, recomienda instalar los que el repo no tiene y deja como preguntas abiertas lo que no sabe.
8. El planificador siempre usa `opus`. El modelo no va en su cabecera (ADR-0002): lo fija la skill `mth-plan` al lanzarlo y no es configurable. `mth models` lo muestra como fijo y el agente avisa si el encargo no declara opus; es un refuerzo, no una garantía, porque el plugin no controla el parámetro `model` de la herramienta Agent.
9. El orquestador instala los agentes del catálogo que el plan acordado recomienda (la persona los aprobó al acordarlo) y reparte el trabajo apoyándose en el plan y en las sugerencias del planificador. No instala ninguno que el plan no recomiende. Toda desviación se anota en el «Registro de ejecución» del plan con su motivo. El reparto del plan es una sugerencia.
10. Las claves nuevas llegan a los repos adoptados por el gap automático `config` de `mth update`: no hay brecha nueva.

## Rechazado

- Plan versionado en git: mezcla trabajo de sesión con historia compartida y duplica la spec.
- Solo un recordatorio en el hook de sesión: se olvida, como pasó con SPEC-0022.
- Gate también para `chore` y `docs`: desproporcionado para cambios triviales (§12).
- Modelo fijo en la cabecera del planificador: contradice ADR-0002.
- Modelo del planificador configurable en `[models]`: se pidió que sea siempre `opus`.
- Planificador en el catálogo: habría que instalarlo antes de poder planificar.
- Citar `PLAN-NNNN` en `Refs:`: `mth` valida esos IDs contra documentos versionados.
- Que el planificador discuta con la persona: un subagente no puede preguntar; la discusión es sobre su borrador.

## Consecuencias

- **+** Los agentes trabajan contra un plan acordado y persistente, no contra la memoria de la sesión.
- **+** El repo despliega el plugin según lo que el plan necesita.
- **−** Una comprobación más antes de abrir rama; los planes no se comparten entre clones.
- **riesgo** Un plan marcado `acordado` editando el fichero a mano → es el camino no soportado; `mth plan agree` valida y es el único que la skill usa.
- **riesgo** El gate fricciona y se apaga → `chore` y `docs` exentos y `required_for` configurable.
- **riesgo** El gate no protege este repo hasta que se publique e instale la versión → hasta entonces, la regla de CLAUDE.md.

## Impone

- [script] `mthlib/plans.py` (formato, estados, validación), `mthlib/flow.py` (gate), `mthlib/cli.py` (`mth plan`), `mthlib/config.py` (`[plans]`, `[roles].planner`), `mthlib/session.py` (estado). `mth doctor` comprueba el rol `planner` con su bucle genérico de roles.
- [criterio] `verificador` compara el diff con el plan acordado de la rama.
