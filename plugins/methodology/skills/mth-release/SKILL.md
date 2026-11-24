---
name: mth-release
description: Publica una versión (development → main con merge commit, tag SemVer, release de GitHub, CHANGELOG desde los fragmentos) o cierra un hotfix como patch. Úsala cuando development reúna features completas y estables, ante un bug en producción, o para reanudar una publicación interrumpida.
---

# Versiones

`mth` es el comando del contexto de sesión (`$MTH`). La publicación es autónoma con la CI en verde (con `autonomy.level` `until-pr` o `supervised`, el guard pide antes la confirmación de la persona).

## Decidir si publicar y con qué nivel (autónomo)

No decides por intuición: lo calcula `mth` (SPEC-0017, ADR-0013). Tras **cada integración en `development`**, ejecuta `mth release --plan` (solo lee; desde `development`). Imprime los fragmentos con su nivel, el nivel resultante, la versión propuesta y una decisión con sus motivos:

| Decisión | Qué haces |
|---|---|
| `publicar` | `mth release`. Con `autonomy.level` `full` sin preguntar; con `until-pr` o `supervised`, el guard pide antes la confirmación de la persona |
| `esperar` | Hay ramas abiertas (`feat`, `fix`, `hotfix`) cuyo contenido puede deber entrar en esta versión: sigue con ese trabajo y vuelve a decidir al integrarlo. Si la rama abierta es independiente y lo ya integrado es estable, puedes publicar igualmente |
| `no publicar` | No hay fragmentos: el mantenimiento (docs, CI, tests, refactor sin cambio de comportamiento) no versiona; se acumula |
| `bloqueado` | Un fragmento declara un nivel por debajo de su mínimo (corrígelo en una rama `chore/`), o el nivel resultante es `major` antes de `1.0.0`: `1.0.0` declara la API estable y lo decide la persona; no uses `--allow-major` por tu cuenta, avísala |

El nivel sigue SemVer: el mayor entre los fragmentos (`feat` → `minor` como mínimo; `fix`, `hotfix` y `security` → `patch`; eliminar funcionalidad → `minor` en `0.y.z` y `major` desde `1.0.0`). Si un cambio rompe compatibilidad sin eliminar nada, declara tú un `bump` mayor en su fragmento: `mth` no puede detectarlo.

## Versión desde development

Cuándo: `mth release --plan` dice `publicar`.

1. `mth changes preview`: muestra la versión calculada (mayor `bump` de los fragmentos) y el changelog resultante. Corrige los fragmentos en una rama `chore/` si hace falta.
2. `mth release`:
   - Tests y `mth trace` sobre `development`; si hay `release.version_files`, comprueba que cada fichero existe y que su patrón aparece exactamente una vez (si no, falla sin modificar nada).
   - Crea `release/vX.Y.Z`, incorpora los fragmentos al `CHANGELOG.md`, los borra y actualiza la versión en los `release.version_files` (commit `chore(release)`).
   - PR a `main` → CI → merge commit → etiqueta anotada `vX.Y.Z` → release de GitHub.
   - PR de vuelta a `development` → merge → borra la rama de release.

## Con `forge` = `gitlab` o `none`

`mth release` hace los gates, calcula la versión, genera el `CHANGELOG.md`, prepara y sube `release/vX.Y.Z` y escribe las notas en `.work/merge-request/`, pero no llama a `gh` ni fusiona. Termina con los pasos manuales (MR a `main` y merge, etiqueta, release en la forja y MR de vuelta a `development`), marcados como hechos o pendientes según git. Muéstraselos a la persona tal cual; cuando los haya hecho, vuelve a ejecutar `mth release`: retoma, marca lo hecho y limpia la rama. `mth hotfix finish` no está soportado con esta forja: falla antes de tocar nada.

## Hotfix

1. `mth branch hotfix <slug> [--spec …]` (desde `main`).
2. Test de regresión y fix; fragmento con `bump: patch`.
3. Revisión (skill `mth-review`).
4. `mth hotfix finish`: mismos gates que una integración, versión patch (con la misma comprobación y actualización de `release.version_files`), publicación en `main` y merge de vuelta a `development`.

`mth doctor` muestra la versión que declara cada fichero de `release.version_files` (✓ coincide con la última etiqueta, ⚠ desfasada, ✗ ausente o patrón no único).

## Si falla a mitad

Ambos comandos son reanudables: corrige la causa (CI en rojo, conflicto en el merge de vuelta) y ejecútalos de nuevo. Retoman desde el último paso completado; nunca crean una segunda versión.
