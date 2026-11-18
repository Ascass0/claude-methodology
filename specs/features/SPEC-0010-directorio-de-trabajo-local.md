# SPEC-0010 · Directorio de trabajo local

- Estado: implementada
- Fecha: 2026-11-18
- ADRs: [ADR-0006](../adr/process/ADR-0006-directorio-de-trabajo-local-excluido-de-git.md)
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0010/AC-NN`. -->

## Contexto

Claude deja sus artefactos de trabajo (planes, manifiestos, cuerpos de PR, informes de revisión y de seguridad, notas) en el scratchpad de la sesión, que no persiste ni tiene estructura. Hace falta un directorio local, estándar en todos los repos adoptados, que nunca se suba a git ([ADR-0006](../adr/process/ADR-0006-directorio-de-trabajo-local-excluido-de-git.md)).

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

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| `work.dirs` inválido (nombre con `/`, mayúsculas, repetido o de serie) | Carga de la configuración | Fail-fast: ningún comando se ejecuta |
| Git ya versiona ficheros bajo `.work/` | `work.ensure`, `mth doctor` | No se crea nada ni se toca el exclude; aviso en la sesión y ✗ en doctor con los ficheros |
| `.work` existe pero no es un directorio | `work.ensure`, `mth doctor` | No se toca; aviso en la sesión y ✗ en doctor |
| No se puede escribir `.git/info/exclude` o crear un directorio | `work.ensure` | Error con la causa; la sesión lo muestra como aviso y sigue |
| `git add` forzado que incluiría `.work/` | Guard | Bloqueado, con el motivo |

## Criterios de aceptación

- **AC-01**: `work.ensure` crea `.work/` con los seis subdirectorios de serie y los de `work.dirs`, y añade `/.work/` a `.git/info/exclude`; después, `git status` no muestra nada de `.work/` aunque contenga ficheros.
- **AC-02**: Ejecutar `work.ensure` dos veces no duplica la línea del exclude ni modifica ficheros existentes en `.work/`.
- **AC-03**: La carga de la configuración rechaza en `work.dirs` un nombre con `/`, con mayúsculas, vacío, repetido o igual a uno de serie.
- **AC-04**: Si git versiona ficheros bajo `.work/` o `.work` no es un directorio, `work.ensure` falla sin crear nada ni tocar el exclude, y `mth doctor` lo marca con ✗.
- **AC-05**: El hook de sesión de un repo adoptado prepara `.work/`; si falla, muestra un aviso y la sesión continúa. En un repo sin adoptar no crea nada.
- **AC-06**: `mth init` deja `.work/` preparado al adoptar.
- **AC-07**: `mth doctor` marca con ✓ un `.work/` completo y excluido, y con ⚠ uno incompleto o sin excluir.
- **AC-08**: El guard bloquea `git add -f .work/x`, `git add --force .`, `git add -f -A` y `git add -f :/`, y deja pasar `git add .` y `git add -f build/x`.
- **AC-09**: Las reglas base de la sesión describen `.work/` y sus subdirectorios.

## Notas

Los nombres de serie son los que pidió la persona usuaria (`plans/`, `merge-request/`, `security-report/`) más tres de uso habitual en el ciclo (`reviews/`, `notes/`, `tmp/`).
