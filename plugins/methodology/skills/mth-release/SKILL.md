---
name: mth-release
description: Publica una versión (development → main con merge commit, tag SemVer, release de GitHub y CHANGELOG generado desde los fragmentos) o cierra un hotfix como versión patch. Úsala cuando development reúna features completas y estables entre sí, cuando haya que corregir un bug en producción, o para reanudar una publicación interrumpida.
---

# Versiones

`mth` es el comando del contexto de sesión (`$MTH`). La publicación es autónoma con la CI en verde (con `autonomy.level` `until-pr` o `supervised`, el guard pide antes la confirmación de la persona).

## Versión desde development

Cuándo: hay fragmentos en `changes/`, las features integradas funcionan en conjunto y no hay trabajo a medias que deba entrar en esta versión.

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
