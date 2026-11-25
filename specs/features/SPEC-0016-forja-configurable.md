# SPEC-0016 · Forja configurable

- Estado: implementada
- Fecha: 2026-11-24
- Formato: compacto
- ADRs: [ADR-0012](../adr/process/ADR-0012-forja-configurable.md), [ADR-0011](../adr/process/ADR-0011-adopcion-deducir-por-defecto-o-preguntar.md)
- Sustituye a: —


## Contexto

- El plugin da por hecho GitHub: en GitLab `mth release` falla en el paso de GitHub, la CI de la metodología no se ejecuta y `mth doctor` pide workflows sin sentido.
- [SPEC-0015](SPEC-0015-adopcion-deducir-por-defecto-o-preguntar.md) lo trató de forma provisional (un remoto que no era `github.com` desactivaba `mth integrate` y `mth release`).
- [ADR-0012](../adr/process/ADR-0012-forja-configurable.md) lo sustituye por una clave de configuración.

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
2. Crear la etiqueta anotada `vX.Y.Z` sobre `main` y subirla, con los comandos exactos, citados para el shell (hecho si la etiqueta está en el remoto y apunta a un commit de `main`).
3. Publicar la release en la forja con las notas del fichero (no comprobable: se muestra siempre).
4. Abrir el MR `main → development` y fusionarlo con merge commit (hecho si `main` ya está en `development`).

Al volver a ejecutar `mth release` retoma, con la rama de release abierta o sin ella (la forja puede borrarla al fusionar: entonces la versión se lee del `CHANGELOG.md` de `main`): recalcula el estado de los pasos y, si 1, 2 y 4 están hechos, borra la rama de release, sincroniza `development` y lo dice.

### `mth hotfix finish` con `gitlab` o `none`

Falla antes de modificar nada, con un error que nombra `forge` y explica que el cierre de hotfix aún no está soportado con esa forja.

### Guard, doctor y plantilla

- El guard bloquea `glab mr merge …` y su alias `glab mr accept …` con el mismo mensaje que `gh pr merge`; otros subcomandos de `glab` pasan.
- El bloqueo no se esquiva con opciones globales (`gh -R owner/repo pr merge`), con un prefijo (`sudo`, `env`, `command`…) ni con `gh api` / `glab api` de escritura sobre un endpoint `…/merge`.
- `mth doctor` con `gitlab` o `none` no comprueba `gh` ni avisa de `ci.required`; con `github`, igual que antes.
- La plantilla `methodology.toml` documenta `forge`.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | `forge` con un valor desconocido | Error de configuración que nombra `forge` y los valores válidos; ningún comando corre | AC-01 |
| FM-02 | Remoto ilegible o sin remoto | `mth survey`: `forge = none`; se deniega la parte de la forja, no se relaja | AC-02 |
| FM-03 | `mth hotfix finish` con `gitlab` o `none` | Error antes de modificar nada | AC-08 |
| FM-04 | `gh` no está instalado y `forge` no es `github` | No se usa: los comandos funcionan igual | AC-05, AC-06, AC-10 |
| FM-05 | Versión ya publicada a mano sin rama de release | Los gates y el cálculo de versión son los de siempre; la persona decide qué hacer con la etiqueta existente | AC-06 |
| FM-06 | Etiqueta ya existente al retomar | El paso 2 se marca hecho y no se vuelve a crear, solo si la etiqueta está en el remoto y apunta a un commit de `main`; una solo local o en otro commit no cuenta y no se borra la rama | AC-07 |
| FM-07 | `main` trae una versión anterior a la última etiqueta, o sin etiqueta histórica | Es historia, no una publicación pendiente: no retiene una release nueva | AC-07 |
| FM-08 | La forja borra la rama de release al fusionar el MR | Sin rama pendiente, `mth` detecta en `main` una versión con la etiqueta sin publicar o sin volver a `development` y retoma esa publicación sin calcular otra versión; mientras `main` no haya vuelto a `development` (o la etiqueta no exista) no se calcula versión nueva: la salida es hacer los pasos que lista | AC-07 |
| FM-09 | Un merge a mano con una opción global, un prefijo o la API de la forja | El guard lo bloquea igual que `gh pr merge` | AC-12 |

## Criterios de aceptación

- **AC-01**: `forge` DEBE aceptar `github` (por defecto), `gitlab` y `none`, y rechazar cualquier otro valor nombrando la clave.
- **AC-02**: La señal `forge` DEBE ser `github` para `github.com`, `gitlab` para `gitlab.com` y hosts con primera etiqueta `gitlab`, y `none` para cualquier otro remoto o ninguno, con las formas `https://`, `ssh://` y `git@host:ruta`, sin revelar usuario ni contraseña de la URL.
- **AC-03**: La pregunta `forja` DEBE estar siempre en el inventario como `deducida`; `mth init --answers` DEBE escribir `forge` (una respuesta explícita lo sustituye) y `mth init` sin respuestas DEBE escribir la forja deducida.
- **AC-04**: SI `forge` no es `github`, ENTONCES `ci` DEBE ser `deducida` (`sin-ci`) y `ci: crear` DEBE rechazarse; `versiones` DEBE ser `deducida` (`continuar`) con etiquetas con prefijo y sin herramienta de publicación y preguntarse en otro caso; el plan previo DEBE marcar `mth integrate` y `mth release` como activas solo en su parte local.
- **AC-05**: MIENTRAS `forge` sea `gitlab` o `none`, `mth integrate` DEBE superar los mismos gates, subir la rama, escribir el título y la descripción en `.work/merge-request/` y mostrar los pasos manuales, sin llamar a `gh` ni fusionar; CUANDO se repite con la rama ya fusionada, DEBE limpiarla.
- **AC-06**: MIENTRAS `forge` sea `gitlab` o `none`, `mth release` DEBE crear la rama de release con el `CHANGELOG.md` y los ficheros de versión, subirla, escribir las notas en `.work/merge-request/` y mostrar los pasos manuales con su estado, sin llamar a `gh`.
- **AC-07**: CUANDO se repite `mth release` con `gitlab` o `none`, `mth` DEBE marcar como hechos los pasos que git confirma y, con todos hechos, borrar la rama de release y sincronizar `development`.
- **AC-08**: MIENTRAS `forge` sea `gitlab` o `none`, `mth hotfix finish` DEBE fallar antes de modificar nada.
- **AC-09**: El guard DEBE bloquear `glab mr merge` y dejar pasar otros subcomandos de `glab`; `gh pr merge` DEBE seguir bloqueado.
- **AC-10**: MIENTRAS `forge` sea `gitlab` o `none`, `mth doctor` NO DEBE comprobar `gh` ni avisar de `ci.required`; con `github` DEBE conservar ambas comprobaciones.
- **AC-11**: MIENTRAS `forge` sea `github`, el flujo de integración, publicación y hotfix NO DEBE cambiar (el test de extremo a extremo existente sigue pasando); con un remoto GitLab, `mth release` DEBE generar el `CHANGELOG.md` y la rama de release sin llamar a `gh` y terminar con los pasos manuales.
- **AC-12**: El guard DEBE bloquear el merge a mano aunque lleve opciones globales de `gh`/`glab` (`-R`, `--repo`, `--hostname`), un prefijo de ejecución (`sudo`, `env`, `command`) o una petición de escritura de `gh api` / `glab api` a un endpoint `…/merge`; las lecturas y los demás subcomandos DEBEN pasar.

## Notas

Modifica la regla provisional de [SPEC-0015](SPEC-0015-adopcion-deducir-por-defecto-o-preguntar.md): su AC-04 (sin GitHub, `versiones` deducida sin efecto y `ci` deducida) pasa a ser el de esta spec (AC-04): solo `ci` se deduce, y `versiones` se pregunta.
