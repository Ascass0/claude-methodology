---
name: mth-release
description: Publica una versión (development → main con merge commit, tag SemVer, release de GitHub y CHANGELOG generado desde los fragmentos) o cierra un hotfix como versión patch. Úsala cuando development reúna features completas y estables entre sí, cuando haya que corregir un bug en producción, o para reanudar una publicación interrumpida.
---

# Versiones

`mth` es el comando del contexto de sesión (`$MTH`). La publicación es autónoma con la CI en verde.

## Versión desde development

Cuándo: hay fragmentos en `changes/`, las features integradas funcionan en conjunto y no hay trabajo a medias que deba entrar en esta versión.

1. `mth changes preview`: muestra la versión calculada (mayor `bump` de los fragmentos) y el changelog resultante. Corrige los fragmentos en una rama `chore/` si hace falta.
2. `mth release`:
   - Tests y `mth trace` sobre `development`.
   - Crea `release/vX.Y.Z`, incorpora los fragmentos al `CHANGELOG.md` y los borra (commit `chore(release)`).
   - PR a `main` → CI → merge commit → etiqueta anotada `vX.Y.Z` → release de GitHub.
   - PR de vuelta a `development` → merge → borra la rama de release.

## Hotfix

1. `mth branch hotfix <slug> [--spec …]` (desde `main`).
2. Test de regresión y fix; fragmento con `bump: patch`.
3. Revisión (skill `mth-review`).
4. `mth hotfix finish`: mismos gates que una integración, versión patch, publicación en `main` y merge de vuelta a `development`.

## Si falla a mitad

Ambos comandos son reanudables: corrige la causa (CI en rojo, conflicto en el merge de vuelta) y ejecútalos de nuevo. Retoman desde el último paso completado; nunca crean una segunda versión.
