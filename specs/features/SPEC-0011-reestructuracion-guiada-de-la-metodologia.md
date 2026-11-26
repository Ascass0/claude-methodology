# SPEC-0011 · Reestructuración guiada de la metodología

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: [ADR-0007](../adr/process/ADR-0007-reestructuracion-reutilizando-la-entrevista-de-adopcion.md)
- Sustituye a: —


## Contexto

- La entrevista de adopción ([SPEC-0004](SPEC-0004-adopcion-guiada.md)) explica cada decisión y la registra en un ADR, pero solo antes de adoptar.
- Revisar la metodología después (entera, un bloque o una decisión) obligaba a editar la configuración a mano ([ADR-0007](../adr/process/ADR-0007-reestructuracion-reutilizando-la-entrevista-de-adopcion.md)).

## Objetivo

1. En un repo adoptado, la persona puede volver a contestar el formulario completo, los bloques que elija o solo lo que quiera cambiar.
2. Las respuestas se validan y se aplican de forma determinista sobre la configuración actual, sin perder nada de lo que no se pregunta.
3. El cambio llega como una rama con la configuración nueva y un ADR que registra qué cambia y por qué.

## Fuera de alcance

- Reescribir historia, mover ramas abiertas o migrar automáticamente las specs a una ruta nueva: son migraciones que hace Opus en la rama, tras aprobar el plan.
- Conservar los comentarios de `.claude/methodology.toml`: el fichero se regenera.
- Repos sin adoptar: para ellos está `mth-init`.

## Comportamiento

### Inventario: `mth survey --reconfigure [--only LISTA] [--json]`

- Solo en un repo adoptado. En uno sin adoptar falla e indica `mth-init`. `mth survey` sin `--reconfigure` sigue negándose en un repo adoptado.
- Ofrece todas las preguntas del catálogo, en su orden, salvo `colision` cuando no hay agentes que colisionen. Cada pregunta lleva su `evidence` (la señal del inventario o «reestructuración») y su `current`: el valor actual de las claves que decide.
- Las preguntas se agrupan en bloques:

| Bloque | Preguntas |
|---|---|
| `flujo` | `ramas`, `commits`, `versiones`, `ci` |
| `documentacion` | `alcance`, `specs`, `decisiones`, `idioma`, `instrucciones` |
| `calidad` | `tests`, `revisores`, `colision` |
| `agente` | `autonomia`, `modelos` |

- `--only` recibe IDs de pregunta o nombres de bloque separados por comas y limita el formulario a ellos. Un nombre desconocido es un error, y también lo es una selección que no deja ninguna pregunta aplicable.
- El perfil es `reconfigure`.

### Aplicación: `mth reconfigure --answers FICHERO [--only LISTA]`

1. Precondiciones: repo adoptado, árbol limpio y sin rama `chore/reconfigure-methodology` local ni remota.
2. Rehace el inventario con el mismo `--only` y valida las respuestas contra él, como `mth init --answers`: cada pregunta ofrecida tiene respuesta, ninguna sobra y cada opción y parámetro son válidos.
3. Aplica las respuestas sobre las tablas del `.claude/methodology.toml` actual con las mismas reglas que la adopción, salvo:
   - `alcance`: `gradual` conserva el `trace.legacy_base` que haya y, si no hay, lo fija en el commit actual de `development`; `completa` lo vacía.
   - `revisores`: la lista de la respuesta sustituye a `review.agents` (en la adopción se añadía a la plantilla).
   - `ramas`: `usar` exige que la rama exista en el remoto. `crear` crea `development` desde `main` si no existe.
   - No se infieren `commands.test`, `ci.required` ni `branches.main` a partir del repo: se conserva lo que hay.
4. Valida la configuración resultante (como al cargarla) y el modo de `hooks.commit_msg` antes de crear nada. `chain` exige un hook ajeno que encadenar: sin él, el hook rechazaría todos los commits.
5. Si la configuración no cambia y ninguna respuesta pide una migración, falla con «nada que cambiar» y no crea nada. Piden migración: `specs` y `decisiones` con `convertir` o `archivar`, `colision` con `renombrar`, `instrucciones` con `metodologia` y `ci` con `crear`.
6. Crea `chore/reconfigure-methodology` desde `development`, escribe la configuración y un ADR de reestructuración en `<paths.adr>/methodology/` y reinstala el hook `commit-msg` con el modo nuevo. Después hace un único commit `chore(methodology): reconfigure claude-methodology` (Refs: el ADR nuevo) y sube la rama.
7. El ADR, en el idioma de `language.docs`, tiene: las preguntas revisadas; una tabla de decisiones (pregunta, opción, efecto, nota); una tabla de cambios de configuración (clave, antes, después); las migraciones pendientes; y la referencia al ADR de adopción o de reestructuración más reciente de `<paths.adr>/methodology/`, si lo hay.
8. Muestra los cambios de configuración y las migraciones pendientes.

### Skill `mth-reconfigure`

Opus pregunta primero el alcance (formulario completo, bloques o un cambio descrito con sus palabras) y lanza `mth survey --reconfigure`. Hace las preguntas del catálogo de `mth-init` indicando el valor actual. Si hay migraciones, presenta un plan y pide aprobación. Guarda las respuestas en `.work/plans/` y ejecuta `mth reconfigure`. Hace las migraciones en la misma rama, comprueba con `mth doctor` y `mth trace`, e integra.

### Autonomía

Con `autonomy.level = "supervised"`, el guard pide confirmación para `mth reconfigure` (crea rama, commit y push).

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Repo sin adoptar | `mth survey --reconfigure` y `mth reconfigure`: error que indica `mth-init`; nada cambia | AC-01 |
| FM-02 | `--only` con un nombre desconocido o sin preguntas aplicables | Error con los nombres válidos | AC-03 |
| FM-03 | Respuestas que faltan, sobran o son inválidas | Error con cada problema; nada cambia | AC-05 |
| FM-04 | Configuración resultante inválida (p. ej. se quita un revisor con `review.paths`) | Error de configuración antes de crear la rama; nada cambia | AC-05 |
| FM-05 | `ramas: usar` con una rama que no existe en el remoto | Error; nada cambia | AC-05 |
| FM-06 | `commits: encadenar` sin hook ajeno que encadenar | Error; nada cambia (el hook rechazaría todos los commits) | AC-05 |
| FM-07 | Nada que cambiar | Error «nada que cambiar»; nada cambia | AC-06 |
| FM-08 | Árbol sucio o la rama de reestructuración ya existe | Error; nada cambia | AC-05 |

## Criterios de aceptación

- **AC-01**: SI el repo no está adoptado, ENTONCES `mth survey --reconfigure` DEBE fallar; SI está adoptado, ENTONCES `mth survey` sin la opción DEBE seguir fallando.
- **AC-02**: CUANDO el repo está adoptado, el inventario de reestructuración DEBE ofrecer todas las preguntas del catálogo en orden (sin `colision` si no hay colisiones), cada una con `current`, con el perfil `reconfigure`.
- **AC-03**: `--only` DEBE aceptar IDs y bloques y rechazar un nombre desconocido o una selección sin preguntas aplicables; los bloques DEBEN cubrir cada pregunta del catálogo exactamente una vez.
- **AC-04**: CUANDO se ejecuta `mth reconfigure`, `mth` DEBE aplicar las respuestas sobre la configuración actual conservando las claves no preguntadas (p. ej. `[ids]` propios, `review.paths`, `work.dirs`) y crear `chore/reconfigure-methodology` con la configuración y el ADR en un único commit subido, con decisiones, cambios de configuración y la referencia al ADR de adopción.
- **AC-05**: SI faltan, sobran o son inválidas las respuestas, la configuración resultante es inválida, `ramas: usar` apunta a una rama inexistente, `commits: encadenar` no tiene hook ajeno, el árbol está sucio o la rama ya existe, ENTONCES `mth reconfigure` DEBE fallar sin crear rama ni modificar ficheros.
- **AC-06**: SI las respuestas no cambian la configuración ni piden migraciones, ENTONCES `mth reconfigure` DEBE fallar con «nada que cambiar»; SI piden una migración, ENTONCES DEBE crear la rama y el ADR DEBE listarla como pendiente.
- **AC-07**: CUANDO `alcance` es `gradual`, `mth` DEBE conservar el `trace.legacy_base` existente o, si no hay, fijarlo en el commit de `development`; CUANDO es `completa`, DEBE vaciarlo; `revisores` DEBE sustituir la lista.
- **AC-08**: CUANDO cambia `commits`, `mth` DEBE reinstalar el hook `commit-msg` con el modo nuevo.
- **AC-09**: MIENTRAS `autonomy.level = "supervised"`, el guard DEBE pedir confirmación para `mth reconfigure`.
- **AC-10**: La skill `mth-reconfigure` DEBE existir y documentar los cuatro bloques y los comandos `mth survey --reconfigure` y `mth reconfigure`, y `mth-init` DEBE remitir a ella en un repo ya adoptado.

## Notas

Lo pidió la persona usuaria para poder volver a «la interacción inicial» de la adopción en cualquier momento.
