# SPEC-0016 · Forja configurable

- Estado: implementada
- Fecha: 2026-11-24
- ADRs: [ADR-0012](../adr/process/ADR-0012-forja-configurable.md), [ADR-0011](../adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md)
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0016/AC-NN`. -->

## Contexto

El plugin da por hecho GitHub. En un repo alojado en GitLab, `mth release` falla en el paso de GitHub, la CI de la metodología no se ejecuta y `mth doctor` pide workflows que no tienen sentido. [SPEC-0015](SPEC-0015-adopcion-deducir-por-defecto-o-preguntar.md) lo trató de forma provisional (un remoto que no era `github.com` desactivaba `mth integrate` y `mth release`). [ADR-0012](../adr/process/ADR-0012-forja-configurable.md) lo sustituye por una clave de configuración.

## Objetivo

1. Una clave `forge` (`github`, `gitlab` o `none`) que `mth survey` deduce del remoto.
2. Con `github`, nada cambia.
3. Con `gitlab` o `none`, `mth integrate` y `mth release` hacen la parte local y terminan con la lista exacta de pasos manuales, sin llamar a `gh` y sin fusionar nunca.
4. El guard bloquea `glab mr merge` como `gh pr merge`.

## Fuera de alcance

- Soporte completo de GitLab: `glab`, estado de los pipelines, releases.
- `mth hotfix finish` con `gitlab` o `none`: falla de forma explícita.
- `mth github` y `mth init --github` (ajustes de merge y ruleset de GitHub): siguen siendo solo de GitHub.

## Comportamiento

### Configuración

`forge` es una clave de primer nivel de `.claude/methodology.toml`. Valores: `github` (por defecto), `gitlab` y `none`. Cualquier otro valor es un error de configuración que nombra la clave.

### Deducción (`mth survey`)

La señal `forge` sale de la URL del remoto (`remote.<nombre>.url`):

| Host | `forge` |
|---|---|
| `github.com` | `github` |
| `gitlab.com`, o con primera etiqueta `gitlab` (`gitlab.empresa.com`) | `gitlab` |
| cualquier otro, o sin remoto | `none` |

Se admiten las formas `https://`, `ssh://` y `git@host:ruta`. Una URL con usuario o contraseña no los revela: la evidencia nombra solo el host.

El inventario añade la pregunta `forja` (siempre presente, en el bloque `flujo` de `mth reconfigure`), con las opciones `github`, `gitlab` y `none`. Siempre es `deducida`: no se pregunta. `mth init --answers` escribe `forge` en la configuración, y una respuesta explícita lo sustituye. `mth init` sin `--answers` también escribe la forja deducida.

Cambios en las demás preguntas, que sustituyen la regla provisional de SPEC-0015:

- `ci`: si `forge` no es `github`, `deducida` (`sin-ci`) y solo se ofrece `sin-ci`.
- `versiones`: deja de ser `deducida` sin efecto (`mth release` funciona en su parte local). Con `gitlab` o `none`, si hay etiquetas con prefijo y ninguna herramienta de publicación (`release_tools`), es `deducida` (`continuar`, con los `version_files` detectados); en otro caso se pregunta, con todas sus opciones. Con `github`, se pregunta como antes.
- Capacidades del plan previo: con `github`, `mth integrate` y `mth release` activas; con otra forja, activas **solo en su parte local** (el motivo lo dice: `forge = gitlab`, el merge y la publicación son manuales).

### `mth integrate` con `gitlab` o `none`

Tras los mismos gates que con GitHub (rama destino, mensajes, fragmento, trazabilidad, revisiones, tests), `mth`:

1. Sube la rama (git).
2. Escribe en `.work/merge-request/<rama>.md` el título y la descripción del MR (la misma descripción que llevaría el PR).
3. No llama a `gh`, no consulta la CI y no fusiona.
4. Termina mostrando los pasos manuales: abrir el MR `rama → destino` con ese título y descripción, esperar a la CI en verde, fusionar con merge commit (sin squash ni rebase) y volver a ejecutar `mth integrate`.

Si se ejecuta de nuevo con la rama ya fusionada en el destino, detecta la integración por git y limpia la rama, igual que con GitHub.

### `mth release` con `gitlab` o `none`

Con los mismos gates y el mismo cálculo de versión que con GitHub, `mth` crea `release/vX.Y.Z`, incorpora los fragmentos al `CHANGELOG.md` y a los `release.version_files`, hace el commit `chore(release)` y sube la rama. Escribe el título y las notas en `.work/merge-request/release-vX.Y.Z.md`. No llama a `gh`.

Después muestra la lista de pasos manuales, cada uno marcado como hecho o pendiente según git:

1. Abrir el MR `release/vX.Y.Z → main` y fusionarlo con merge commit tras la CI en verde (hecho si la rama ya está en `main`).
2. Crear la etiqueta anotada `vX.Y.Z` sobre `main` y subirla, con los comandos exactos (hecho si la etiqueta existe).
3. Publicar la release en la forja con las notas del fichero (no comprobable: se muestra siempre).
4. Abrir el MR `main → development` y fusionarlo con merge commit (hecho si `main` ya está en `development`).

Al volver a ejecutar `mth release` con la rama de release ya abierta, retoma: recalcula el estado de los pasos y, si 1, 2 y 4 están hechos, borra la rama de release, sincroniza `development` y lo dice.

### `mth hotfix finish` con `gitlab` o `none`

Falla antes de modificar nada, con un error que nombra `forge` y explica que el cierre de hotfix aún no está soportado con esa forja.

### Guard, doctor y plantilla

- El guard bloquea `glab mr merge …` con el mismo mensaje que `gh pr merge`; otros subcomandos de `glab` pasan.
- `mth doctor` con `gitlab` o `none` no comprueba `gh` ni avisa de `ci.required`; con `github`, igual que antes.
- La plantilla `methodology.toml` documenta `forge`.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| `forge` con un valor desconocido | Carga de la configuración | Error que nombra `forge` y los valores válidos; ningún comando corre |
| Remoto ilegible o sin remoto | `mth survey` | `forge = none`: se deniega la parte de la forja, no se relaja |
| `mth hotfix finish` con `gitlab` o `none` | `mth hotfix finish` | Error antes de modificar nada |
| `gh` no está instalado y `forge` no es `github` | `mth integrate`, `mth release` | No se usa: los comandos funcionan igual |
| Versión ya publicada a mano sin rama de release | `mth release` | Los gates y el cálculo de versión son los de siempre: la persona decide qué hacer con la etiqueta existente |
| Etiqueta ya existente al retomar | `mth release` | El paso 2 se marca como hecho y no se vuelve a crear |

## Criterios de aceptación

- **AC-01**: `forge` acepta `github` (por defecto), `gitlab` y `none`, y rechaza cualquier otro valor nombrando la clave.
- **AC-02**: La señal `forge` es `github` para `github.com`, `gitlab` para `gitlab.com` y para hosts con primera etiqueta `gitlab`, y `none` para cualquier otro remoto o ninguno, con las formas `https://`, `ssh://` y `git@host:ruta`, sin revelar usuario ni contraseña de la URL.
- **AC-03**: La pregunta `forja` está siempre en el inventario como `deducida`, `mth init --answers` escribe `forge` (y una respuesta explícita lo sustituye) y `mth init` sin respuestas escribe la forja deducida.
- **AC-04**: Con `forge` distinto de `github`, `ci` es `deducida` (`sin-ci`) y `ci: crear` se rechaza; `versiones` es `deducida` (`continuar`) con etiquetas con prefijo y sin herramienta de publicación, y se pregunta en otro caso; el plan previo marca `mth integrate` y `mth release` como activas solo en su parte local.
- **AC-05**: Con `gitlab` o `none`, `mth integrate` supera los mismos gates, sube la rama, escribe el título y la descripción en `.work/merge-request/`, muestra los pasos manuales, no llama a `gh` ni fusiona, y al repetirse con la rama ya fusionada limpia.
- **AC-06**: Con `gitlab` o `none`, `mth release` crea la rama de release con el `CHANGELOG.md` y los ficheros de versión, la sube, escribe las notas en `.work/merge-request/`, muestra los pasos manuales con su estado y no llama a `gh`.
- **AC-07**: Al repetir `mth release` con `gitlab` o `none`, marca como hechos los pasos que git confirma y, con todos hechos, borra la rama de release y sincroniza `development`.
- **AC-08**: Con `gitlab` o `none`, `mth hotfix finish` falla antes de modificar nada.
- **AC-09**: El guard bloquea `glab mr merge` y deja pasar otros subcomandos de `glab`; `gh pr merge` sigue bloqueado.
- **AC-10**: `mth doctor` con `gitlab` o `none` no comprueba `gh` ni avisa de `ci.required`, y con `github` conserva ambas comprobaciones.
- **AC-11**: Con `github` el flujo de integración, publicación y hotfix no cambia (el test de extremo a extremo existente sigue pasando); con un remoto GitLab, `mth release` genera el `CHANGELOG.md` y la rama de release sin llamar a `gh` y termina con los pasos manuales.

## Notas

Modifica la regla provisional de [SPEC-0015](SPEC-0015-adopcion-deducir-por-defecto-o-preguntar.md): su AC-04 (sin GitHub, `versiones` deducida sin efecto y `ci` deducida) pasa a ser el de esta spec (AC-04): solo `ci` se deduce, y `versiones` se pregunta.
