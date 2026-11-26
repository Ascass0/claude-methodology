# SPEC-0023 · Planes acordados antes de desarrollar

- Estado: implementada
- Fecha: 2026-11-26
- Formato: compacto
- ADRs: [ADR-0021](../adr/process/ADR-0021-planes-acordados-antes-de-desarrollar.md)
- Sustituye a: —

## Contexto

- Toda idea necesita un plan discutido con la persona, guardado y consultable por los agentes antes de crear rama, spec o código.
- [ADR-0021](../adr/process/ADR-0021-planes-acordados-antes-de-desarrollar.md) fija el fichero local, el gate y el reparto de papeles entre hilo principal, planificador, persona y orquestador.

## Objetivo

1. Una rama `feat`, `fix` o `hotfix` no se crea ni se integra sin un plan acordado.
2. El plan lo redacta el planificador con los agentes del catálogo y recomienda instalar los que falten.
3. El orquestador reparte el trabajo apoyándose en el plan y deja constancia de lo que hizo.

## Fuera de alcance

- Versionar los planes o compartirlos entre clones o CI.
- Ejecutar el plan automáticamente.
- Un plan para `chore` y `docs`.
- Cambiar el «Plan de trabajo» de una spec ([SPEC-0001](SPEC-0001-delegacion-verificable.md)).

## Comportamiento

### Configuración

| Clave | Por defecto | Significa |
|---|---|---|
| `plans.required_for` | `["feat", "fix", "hotfix"]` | Tipos de rama que necesitan plan acordado |
| `roles.planner` | `""` (la plantilla trae `"planificador"`, como los demás roles) | Agente del plugin que redacta los planes |

### Fichero de plan

- Ruta `.work/plans/PLAN-NNNN-<slug>.md`: `NNNN` es el mayor número existente más uno, con cuatro cifras.
- Cabecera con `- Estado:`, `- Fecha:`, `- Acordado con:`, `- Refs:` y `- Rama:` (una o varias ramas).
- Secciones de un plan ejecutable, en este orden: `Idea`, `Decisiones acordadas`, `Fuera de alcance`, `Tareas`, `Agentes a instalar`, `Verificación y cierre`, `Riesgos`, `Preguntas abiertas` y `Registro de ejecución`.
- Una hoja de ruta cambia `Tareas`, `Agentes a instalar` y `Verificación y cierre` por una sección `Fases` (cada fase tiene después su propio plan): `Idea`, `Decisiones acordadas`, `Fases`, `Fuera de alcance`, `Riesgos`, `Preguntas abiertas` y `Registro de ejecución`.
- El formato del plan no depende de `language.docs`.
- `Tareas`: tabla `| Tarea | Oleada | Agente sugerido | Depende de | Ficheros | Hecho cuando |`, hasta 50 tareas.
- Estados: `borrador`, `acordado`, `en curso`, `ejecutado`, `abandonado`.

### `mth plan`

| Acción | Efecto |
|---|---|
| `new <slug>` | Crea el plan en `borrador` con la plantilla y muestra su ruta |
| `agree PLAN-NNNN` | Valida el plan y, si es válido, pasa a `acordado` con la fecha |
| `list` | Lista los planes con ID, estado, título y ramas |
| `show PLAN-NNNN` | Imprime el plan |
| `done PLAN-NNNN [--abandon]` | Pasa a `ejecutado`, o a `abandonado` con `--abandon` |

- Validación de `agree`: secciones obligatorias presentes, `Preguntas abiertas` sin pendientes («Ninguna»), IDs de tarea únicos, `Depende de` con tareas que existen y sin ciclos, la oleada de una tarea mayor que la de sus dependencias, ficheros disjuntos dentro de una oleada (mismas reglas de solape que `mth plan check`).
- Transiciones: `borrador` → `acordado` → `en curso` → `ejecutado`; también `acordado` → `ejecutado` (una hoja de ruta no abre rama propia); `abandonado` desde cualquier estado distinto de `ejecutado`. Cualquier otra se rechaza.
- Las acciones `check`, `verify`, `model` y `stats` siguen siendo las del «Plan de trabajo» de una spec.

### Gate

- `mth branch <tipo> <slug> --plan PLAN-NNNN`: para un tipo de `plans.required_for` exige el plan `acordado` o `en curso`, añade la rama a `- Rama:` y pasa el plan a `en curso`.
- `mth integrate` y `mth hotfix finish`: para un tipo de `plans.required_for` exigen un plan `en curso` que liste la rama de primer nivel. Las ramas hijas usan el de su padre.
- El gate no depende de `autonomy.level`.

### Estado y diagnóstico

- El hook de sesión y `mth status` listan los planes `acordado` y `en curso` y el de la rama actual; avisan si una rama de un tipo de `plans.required_for` no tiene plan.
- `mth doctor` comprueba el rol `planner` como los demás roles.

### Agentes y skill

- `agents/planificador.md`: agente del plugin de solo lectura, sin `model` en la cabecera. Lee el catálogo con `mth agents list`, asigna solo agentes del catálogo, recomienda instalar en `Agentes a instalar` los que el repo no tiene, no asigna los de requisitos sin cumplir y deja como preguntas abiertas lo que no sabe.
- Skill `mth-plan`: reúne el contexto, lanza el planificador con `model: opus`, presenta el borrador, lo itera con la persona y ejecuta `mth plan agree` solo con su visto bueno.
- Orquestador (catálogo): lee el plan acordado de la rama, no empieza sin él, instala con `mth agents add` los agentes del catálogo que el plan recomienda (y solo esos), sigue oleadas y dependencias, pasa el plan y la tarea en cada encargo y anota desviaciones en el `Registro de ejecución`.
- Verificador: recibe el plan acordado y avisa como hallazgo (en `HALLAZGOS`, sin secciones nuevas) si el diff se sale de él.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Rama de un tipo obligatorio sin `--plan` | `mth branch` falla indicando `mth plan new` y la skill `mth-plan`; no crea la rama | AC-09 |
| FM-02 | Plan en `borrador`, `ejecutado` o `abandonado` | El gate falla nombrando el estado | AC-09 |
| FM-03 | Fichero de plan ilegible, corrupto o inexistente | Error que nombra el fichero; no cuenta como plan acordado | AC-12 |
| FM-04 | Dos sesiones crean un plan a la vez | Creación exclusiva: la segunda toma el número siguiente | AC-02 |
| FM-05 | Plan editado a mano a `acordado` | Riesgo aceptado: `agree` es el camino soportado y valida el plan | AC-04 |
| FM-06 | Plan con preguntas abiertas | `agree` falla listándolas | AC-04 |
| FM-07 | Tareas con ciclo, dependencia inexistente, oleada incoherente o ficheros solapados | `agree` falla con la línea | AC-05 |
| FM-08 | `.work/plans/` no existe en un clon nuevo | El gate falla indicando `mth plan new`; el hook de sesión crea el directorio | AC-10 |
| FM-09 | Transición de estado inválida | Error que nombra el estado actual y el pedido | AC-07 |
| FM-10 | No se puede registrar la rama en el plan al crearla | `mth branch` falla antes de crear la rama: el registro es el primer cambio | AC-09 |
| FM-11 | Dos sesiones modifican el mismo plan a la vez | Riesgo aceptado: la ventana es una lectura y una escritura atómica y `add_branch` se puede repetir | AC-09 |
| FM-12 | Título con saltos de línea o caracteres de control (inyección de campos de cabecera) | `mth plan new` lo rechaza; los campos de cabecera solo se leen de la cabecera | AC-02 |
| FM-13 | Plan de más de 256 KB | Se trata como ilegible | AC-12 |
| FM-14 | Dos ficheros con el mismo `PLAN-NNNN` | `mth` falla nombrándolos | AC-03 |

## Criterios de aceptación

- **AC-01**: SI `plans.required_for` contiene un tipo de rama desconocido, o `roles.planner` no es un texto, ENTONCES la carga de la configuración DEBE fallar nombrando la clave; sin ellas, DEBE usar los valores por defecto.
- **AC-02**: CUANDO se ejecuta `mth plan new <slug>`, `mth` DEBE crear `PLAN-NNNN-<slug>.md` en `borrador` con el mayor número más uno y SI el fichero ya existe DEBE tomar el siguiente; SI el título está vacío, pasa de 120 caracteres o contiene saltos de línea o caracteres de control, ENTONCES DEBE rechazarlo, y los campos de cabecera DEBEN leerse solo de la cabecera.
- **AC-03**: `mth plan list` DEBE listar ID, estado, título y ramas de cada plan, y `mth plan show PLAN-NNNN` DEBE imprimirlo aunque no siga el formato; SI dos ficheros tienen el mismo `PLAN-NNNN`, ENTONCES `mth` DEBE fallar nombrándolos.
- **AC-04**: CUANDO se ejecuta `mth plan agree`, `mth` DEBE pasar el plan válido a `acordado` con la fecha, y SI tiene preguntas abiertas o le faltan secciones, ENTONCES DEBE fallar listándolas sin cambiar el estado.
- **AC-05**: SI las tareas tienen un ID repetido, una dependencia inexistente, un ciclo, una oleada no mayor que la de sus dependencias, ficheros solapados en una oleada o más de 50 tareas, ENTONCES `mth plan agree` DEBE fallar indicando la línea.
- **AC-06**: `mth plan check`, `verify`, `model` y `stats` DEBEN seguir funcionando sobre el «Plan de trabajo» de una spec sin cambios.
- **AC-07**: `mth plan done` DEBE pasar el plan a `ejecutado` o, con `--abandon`, a `abandonado`, y DEBE rechazar toda transición no admitida nombrando el estado actual.
- **AC-08**: `mth` NO DEBE aceptar un `PLAN-NNNN` como referencia en un commit.
- **AC-09**: SI el tipo de rama está en `plans.required_for`, ENTONCES `mth branch` DEBE exigir `--plan` con un plan `acordado` o `en curso`, y fallar sin crear la rama en los demás casos; con un plan válido DEBE añadir la rama al plan y pasarlo a `en curso` antes de crear la rama, y SI no puede escribirlo, ENTONCES DEBE fallar sin crearla.
- **AC-10**: SI el tipo de rama está en `plans.required_for`, ENTONCES `mth integrate` y `mth hotfix finish` DEBEN exigir un plan `en curso` que liste la rama de primer nivel y fallar cerrado sin él, también en una rama hija sin el plan de su padre.
- **AC-11**: El gate DEBE aplicarse igual con cualquier `autonomy.level`.
- **AC-12**: SI un fichero de plan es ilegible, pesa más de 256 KB o no sigue el formato, ENTONCES `mth` DEBE fallar nombrando el fichero y NO DEBE contarlo como plan acordado.
- **AC-13**: El hook de sesión y `mth status` DEBEN listar los planes `acordado` y `en curso` y avisar de una rama obligatoria sin plan.
- **AC-14**: `mth doctor` DEBE comprobar el agente del rol `planner`.
- **AC-15**: `agents/planificador.md` DEBE existir sin `model` en su cabecera ni herramientas de escritura, y su texto DEBE exigir leer el catálogo con `mth agents list`, asignar solo agentes del catálogo, recomendar instalar los que falten con motivo y tarea, no asignar los de requisitos sin cumplir y dejar como pregunta abierta lo que no sepa.
- **AC-16**: La skill `mth-plan` DEBE existir, lanzar el planificador con `model: opus` y ejecutar `mth plan agree` solo con el visto bueno de la persona.
- **AC-17**: El texto del orquestador DEBE exigir el plan acordado, instalar los agentes del catálogo que el plan recomienda y ninguno más, las oleadas y dependencias, pasar plan y tarea en cada encargo y anotar las desviaciones en el `Registro de ejecución`; el texto del verificador DEBE pedir el aviso de desvío del plan como hallazgo.
- **AC-18**: Las claves `[plans]` y `[roles].planner` DEBEN llegar a un repo adoptado por el gap `config` de `mth update` sin una brecha nueva.
- **AC-20**: `mth` DEBE registrar en su traza cada transición de plan y cada denegación del gate de integración.
- **AC-19**: El ciclo de `context/core.md`, `mth-develop`, `mth-branch`, el README y el catálogo de agentes DEBEN incluir el plan acordado y el planificador.

## Notas

- Numeración: el ADR de este cambio es ADR-0021 y la spec SPEC-0023.
- Enmiendas en la misma rama: SPEC-0010 (`plans/` incluye los PLAN), SPEC-0001 (`mth plan` tiene dos familias de acciones) y SPEC-0004 (agentes del plugin).
- Las plantillas del catálogo no citan IDs del plugin (SPEC-0012/AC-28): el texto del orquestador no cita esta spec.
- El gate no protege este repo hasta que se publique e instale la versión; hasta entonces vale la regla de CLAUDE.md.
