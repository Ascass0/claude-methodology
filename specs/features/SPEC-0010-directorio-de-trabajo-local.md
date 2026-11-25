# SPEC-0010 · Directorio de trabajo local

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: [ADR-0006](../adr/process/ADR-0006-directorio-de-trabajo-local-excluido-de-git.md)
- Sustituye a: —


## Contexto

- Claude deja sus artefactos de trabajo (planes, manifiestos, cuerpos de PR, informes de revisión y de seguridad, notas) en el scratchpad de la sesión: no persiste ni tiene estructura.
- Hace falta un directorio local, estándar en todos los repos adoptados, que nunca se suba a git ([ADR-0006](../adr/process/ADR-0006-directorio-de-trabajo-local-excluido-de-git.md)).

## Objetivo

1. Todo repo adoptado tiene `.work/` con sus subdirectorios, excluido de git, sin que el plugin modifique ficheros versionados.
2. Las reglas y las skills dicen a Claude qué guardar en cada subdirectorio.
3. Nada de `.work/` llega a un commit por un descuido habitual.

## Fuera de alcance

- Limpiar `tmp/` o cualquier otro subdirectorio: el contenido es de quien trabaja.
- Sincronizar `.work/` entre máquinas.
- Repos sin adoptar: el plugin no actúa en ellos (SPEC-0004).

## Comportamiento

### Estructura

`.work/` en la raíz del repo, con estos subdirectorios de serie:

| Subdirectorio | Contenido |
|---|---|
| `plans/` | planes de trabajo, manifiestos de agentes y borradores de diseño |
| `merge-request/` | títulos, resúmenes y cuerpos de PR |
| `security-report/` | informes de seguridad |
| `reviews/` | informes completos de los revisores |
| `notes/` | notas de sesión que se conservan |
| `tmp/` | temporales desechables: se pueden borrar en cualquier momento |

`work.dirs` (lista, vacía por defecto) añade subdirectorios propios del repo. Cada nombre es un único segmento en minúsculas (`^[a-z0-9][a-z0-9._-]*$`), sin repetir y distinto de los de serie. Un valor inválido es fail-fast al cargar la configuración.

### Preparación

`work.ensure` crea `.work/` y cada subdirectorio que falte, y añade `/.work/` a `.git/info/exclude` (la ruta que da `git rev-parse --git-path info/exclude`, que también vale en worktrees) si no hay ya una línea que lo excluya. Es idempotente: no duplica la línea ni toca lo que ya existe. Lo ejecutan:

- el hook de sesión, en cada sesión de un repo adoptado (si falla, avisa en el estado sin romper la sesión);
- `mth init`, al adoptar.

### Diagnóstico

`mth doctor` muestra ✓ si `.work/` existe, tiene todos los subdirectorios y está excluido; ⚠ si falta algo (lo arregla la siguiente sesión); y ✗ si git tiene ficheros versionados bajo `.work/`.

### Guard

El guard bloquea `git add -f` / `--force` cuando algún argumento es `.work` o está dentro de `.work/`, o cuando añade el árbol entero (`.`, `./`, `:/`, `*`, `-A`, `--all`): un `add` forzado del árbol incluiría los ficheros excluidos.

### Uso

Las reglas base de la sesión describen `.work/` y sus subdirectorios. `mth-review` guarda los informes en `.work/reviews/`, `mth-develop` los manifiestos en `.work/plans/` y `mth-integrate` el resumen del PR en `.work/merge-request/`.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | `work.dirs` inválido (nombre con `/`, mayúsculas, repetido o de serie) | Fail-fast al cargar la configuración | AC-03 |
| FM-02 | Git ya versiona ficheros bajo `.work/` | `work.ensure` y `mth doctor`: no se crea nada ni se toca el exclude; aviso en la sesión y ✗ en doctor con los ficheros | AC-04 |
| FM-03 | `.work` existe pero no es un directorio | No se toca; aviso en la sesión y ✗ en doctor | AC-04 |
| FM-04 | No se puede escribir `.git/info/exclude` o crear un directorio | `work.ensure`: error con la causa; la sesión lo muestra como aviso y sigue | AC-05 |
| FM-05 | `git add` forzado que incluiría `.work/` | El guard lo bloquea con el motivo | AC-08 |

## Criterios de aceptación

- **AC-01**: CUANDO se ejecuta `work.ensure`, `mth` DEBE crear `.work/` con los seis subdirectorios de serie y los de `work.dirs` y añadir `/.work/` a `.git/info/exclude`, de modo que `git status` no muestre nada de `.work/` aunque contenga ficheros.
- **AC-02**: CUANDO se ejecuta `work.ensure` dos veces, `mth` NO DEBE duplicar la línea del exclude ni modificar ficheros existentes en `.work/`.
- **AC-03**: SI un nombre de `work.dirs` tiene `/`, mayúsculas, está vacío, repetido o es uno de serie, ENTONCES la carga de la configuración DEBE rechazarlo.
- **AC-04**: SI git versiona ficheros bajo `.work/` o `.work` no es un directorio, ENTONCES `work.ensure` DEBE fallar sin crear nada ni tocar el exclude y `mth doctor` DEBE marcarlo con ✗.
- **AC-05**: CUANDO empieza una sesión en un repo adoptado, el hook DEBE preparar `.work/`; SI falla, ENTONCES DEBE avisar y la sesión DEBE continuar; en un repo sin adoptar NO DEBE crear nada.
- **AC-06**: CUANDO se ejecuta `mth init`, `mth` DEBE dejar `.work/` preparado.
- **AC-07**: CUANDO se ejecuta `mth doctor`, `mth` DEBE marcar con ✓ un `.work/` completo y excluido y con ⚠ uno incompleto o sin excluir.
- **AC-08**: El guard DEBE bloquear `git add -f .work/x`, `git add --force .`, `git add -f -A` y `git add -f :/`, y DEBE dejar pasar `git add .` y `git add -f build/x`.
- **AC-09**: Las reglas base de la sesión DEBEN describir `.work/` y sus subdirectorios.

## Notas

Los nombres de serie son los que pidió la persona usuaria (`plans/`, `merge-request/`, `security-report/`) más tres de uso habitual en el ciclo (`reviews/`, `notes/`, `tmp/`).
