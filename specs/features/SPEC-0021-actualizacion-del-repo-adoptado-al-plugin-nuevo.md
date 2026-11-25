# SPEC-0021 · Actualización del repo adoptado al plugin nuevo

- Estado: borrador
- Fecha: 2026-11-25
- Formato: compacto
- ADRs: ADR-0017
- Sustituye a: —

## Contexto

- La adopción ([SPEC-0004](SPEC-0004-adopcion-guiada.md)) y la reestructuración ([SPEC-0011](SPEC-0011-reestructuracion-guiada-de-la-metodologia.md)) parten de decisiones de la persona. Ninguna cubre el caso en que el repo ya está adoptado y es el **plugin** el que ha cambiado.
- Cada versión puede exigir más a un repo adoptado: claves de configuración, agentes del catálogo, formato de specs y ADR, bloque de CLAUDE.md, hooks.
- `mth doctor` y `mth agents list` detectan piezas sueltas, pero nada las reúne ni las aplica. Hasta ahora lo hacía la persona explicándoselo a Claude cada vez.
- Este repo desarrolla el plugin y se aplica su propia metodología: es el primer usuario de esta operación.
- Decisión: [ADR-0017](../adr/process/ADR-0017-actualizacion-de-un-repo-adoptado-por-brechas-deterministas.md).

## Objetivo

1. `mth update --plan` lista, sin escribir nada, las **brechas** entre el repo y lo que exige el plugin instalado.
2. `mth update` aplica en una rama las brechas deterministas y deja un ADR de actualización.
3. La skill `mth-update`, invocada por la persona, conduce lo que requiere criterio (decisiones y migraciones) hasta integrar.
4. Actualizar nunca cambia una decisión ya tomada: para eso está `mth reconfigure`.

## Fuera de alcance

- Proponer la actualización al abrir una sesión: la skill se usa solo cuando la persona la invoca.
- Cambiar valores de configuración existentes o preguntas de la adopción ([SPEC-0011](SPEC-0011-reestructuracion-guiada-de-la-metodologia.md)).
- Registrar la versión del plugin aplicada en `methodology.toml`: el diagnóstico se basa en brechas, no en versiones (ADR-0017).
- Publicar una versión del repo.
- Convertir documentos de forma automática: es una migración con aprobación.

## Comportamiento

### Brechas

Cada brecha tiene `id`, `clase`, `evidencia` y `acción`. Clases:

| Clase | Significado |
|---|---|
| `automatica` | `mth update` la aplica sin criterio humano y sin cambiar nada decidido |
| `decision` | Depende de la persona o es una migración; la conduce la skill con aprobación |
| `informativa` | Se muestra; `mth` no la aplica (coste, tokens o trabajo de tests) |

Registro inicial:

| ID | Brecha | Evidencia | Clase | Acción |
|---|---|---|---|---|
| `config` | Claves del esquema ausentes de `methodology.toml` | Comparación con `templates/methodology.toml` | `automatica` | Añadir la tabla o clave con su valor por defecto |
| `agentes-desactualizados` | Agente del catálogo desactualizado | `mth agents list` | `automatica` | `mth agents sync` |
| `agentes-editados` | Agente con la parte generada editada a mano | Hash de la cabecera | `decision` | Elegir entre `--force` y conservar |
| `agentes-perfil` | Agentes del perfil `base` sin instalar | `mth agents list` | `decision` | `mth agents add` de los que acepte la persona |
| `bloque` | Bloque de CLAUDE.md distinto del de la plantilla | Comparación del bloque | `automatica` | Regenerar el bloque |
| `hook` | Hook `commit-msg` de la metodología desactualizado | `mth doctor` | `automatica` | Reinstalar según `hooks.commit_msg` |
| `formato` | Specs y ADR sin `Formato: compacto` | Cuenta por documento | `decision` | Migración: convertir o dejar como están |
| `humo` | Sin registro de `mth smoke` o de otra versión de Claude Code | `mth doctor` | `informativa` | Ejecutar `mth smoke` |
| `triangulacion` | Criterios con un único test | `mth trace --single` | `informativa` | Trabajo de tests por spec |

### `mth update --plan [--json]`

- Solo lee. En un repo sin adoptar falla e indica `mth-init`.
- Imprime cada brecha con su clase, evidencia y acción, agrupadas por clase, y la versión del plugin.
- Sin brechas, imprime «al día».

### `mth update`

1. Precondiciones: repo adoptado, árbol limpio y sin rama `chore/update-methodology` local ni remota. Si ya se está en esa rama, la operación se reanuda y solo aplica lo que falta.
2. Aplica solo las brechas `automatica`. Una brecha que no puede aplicarse sin pisar algo (p. ej. un agente editado a mano) pasa a `decision`.
3. Las claves nuevas se añaden con su valor por defecto; NO modifica ningún valor existente.
4. Crea `chore/update-methodology` desde `development`, un único commit `chore(methodology): update claude-methodology` y sube la rama.
5. Escribe un ADR de actualización en `<paths.adr>/methodology/`, en el idioma de `language.docs`: versión del plugin, brechas aplicadas y brechas pendientes (`decision` e `informativa`), y referencia al ADR de adopción o reestructuración más reciente.
6. Muestra lo aplicado y lo pendiente. Sin brechas `automatica`, falla con «nada que aplicar» y sin crear nada.

### Skill `mth-update`

- Frontmatter con `model: opus` y sin disparo automático: solo la lanza la persona. El hook de sesión NO la propone.
- Flujo: `mth update --plan`; presentar las brechas; `mth update`; preguntar en una sola ronda las `decision` (agentes del perfil, conversión de documentos, agentes editados); plan de migración aprobado antes de convertir documentos; ejecutar en la misma rama con commits `chore` o `docs`; `mth doctor` sin ✗ y `mth trace` sin errores; integrar con `mth-integrate`.
- Cierra con tres listas: aplicado, decidido y pendiente (informativas).
- Si se detiene una migración tras tres rondas de ajuste sin acuerdo, resume lo pendiente y no integra.

### Mantenimiento del registro

- Una spec que añada una exigencia a los repos adoptados DEBE añadir su brecha al registro en la misma rama.
- `revisor-adr` lo comprueba en el diff.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Repo sin adoptar | `mth update` y `--plan`: error que indica `mth-init`; nada cambia | AC-01 |
| FM-02 | Árbol sucio o rama de actualización ya existente (fuera de ella) | Error; nada cambia | AC-07 |
| FM-03 | Configuración ilegible o inválida | Error de configuración con su pista; nada cambia | AC-07 |
| FM-04 | Agente editado a mano | No se sobrescribe: pasa a `decision` | AC-04 |
| FM-05 | Fallo a mitad de la aplicación | La operación es reanudable: re-ejecutar en la rama aplica solo lo que falta | AC-09 |
| FM-06 | Nada que aplicar | Error «nada que aplicar»; no se crea rama | AC-08 |
| FM-07 | Claude Code no tiene `claude` para el humo | La brecha `humo` es informativa; nunca bloquea | AC-10 |

## Criterios de aceptación

- **AC-01**: SI el repo no está adoptado, ENTONCES `mth update` y `mth update --plan` DEBEN fallar indicando `mth-init` sin modificar nada.
- **AC-02**: CUANDO se ejecuta `mth update --plan`, `mth` DEBE listar cada brecha con `id`, clase, evidencia y acción, sin modificar nada (ramas, ficheros ni configuración); sin brechas, DEBE imprimir «al día».
- **AC-03**: SI faltan claves del esquema en `methodology.toml`, ENTONCES `mth update --plan` DEBE listarlas como `config` (`automatica`) y `mth update` DEBE añadirlas con su valor por defecto sin cambiar ninguno existente.
- **AC-04**: SI un agente del catálogo está desactualizado, ENTONCES DEBE listarse como `automatica` y sincronizarse; SI su parte generada está editada a mano, ENTONCES DEBE listarse como `decision` y NO DEBE sobrescribirse; los agentes del perfil `base` sin instalar DEBEN listarse como `decision`.
- **AC-05**: SI hay specs o ADR sin `Formato: compacto`, ENTONCES `mth update --plan` DEBE listar la cuenta como `formato` (`decision`) y `mth update` NO DEBE convertirlos.
- **AC-06**: SI el bloque de CLAUDE.md o el hook `commit-msg` difieren de la plantilla, ENTONCES DEBEN listarse como `automatica` y `mth update` DEBE regenerarlos.
- **AC-07**: CUANDO se ejecuta `mth update` con el árbol sucio, fuera de `chore/update-methodology` con esa rama existente, o con configuración inválida, `mth` DEBE fallar sin crear rama ni modificar ficheros.
- **AC-08**: CUANDO se ejecuta `mth update` con brechas `automatica`, `mth` DEBE crear `chore/update-methodology` desde `development` con un único commit que incluye lo aplicado y el ADR de actualización (versión del plugin, brechas aplicadas y pendientes), y subir la rama; SI no hay brechas `automatica`, ENTONCES DEBE fallar con «nada que aplicar» sin crear nada.
- **AC-09**: CUANDO se vuelve a ejecutar `mth update` en `chore/update-methodology` o tras aplicar, `mth` DEBE aplicar solo lo que falta y `--plan` NO DEBE listar las brechas `automatica` ya aplicadas.
- **AC-10**: Las brechas `informativa` (`humo`, `triangulacion`) NO DEBEN aplicarse ni bloquear nunca `mth update`.
- **AC-11**: El registro de brechas DEBE definir, para cada brecha, `id`, clase, evidencia y acción, con IDs únicos y una clase válida.
- **AC-12**: La skill `mth-update` DEBE existir con `model: opus` y sin disparo automático, el hook de sesión NO DEBE proponerla y DEBE documentar el flujo y las tres listas de cierre.

## Notas

- Al implementar, comprobar en la documentación de Claude Code la clave de frontmatter que impide el disparo automático de una skill (AC-12).
- Orden de ramas hijas previsto: registro de brechas y `mth update --plan`, después `mth update`, después la skill.
