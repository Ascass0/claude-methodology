# SPEC-0003 · Ficheros de versión en la publicación

- Estado: implementada
- Fecha: 2026-11-18
- ADRs: —
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0003/AC-NN`. -->

## Contexto

`mth release` y `mth hotfix finish` calculan la versión, crean la etiqueta y actualizan el CHANGELOG, pero no tocan los ficheros en los que el proyecto declara su propia versión: un `package.json`, un `pyproject.toml` o, en este repo, `plugin.json`, `marketplace.json` y `mthlib/__init__.py`. Esos ficheros se actualizaban a mano.

En la 0.5.0 nadie lo hizo. Se publicó declarando 0.4.0, y como Claude Code actualiza los plugins por versión, quien ya tenía el plugin instalado no recibió la actualización. La v0.5.1 corrigió los ficheros, pero no la causa: la próxima versión fallaría igual.

## Objetivo

1. El repo declara en su configuración qué ficheros contienen la versión y dónde.
2. Publicar una versión (normal o hotfix) actualiza esos ficheros en el mismo commit que el CHANGELOG.
3. Una declaración rota o desfasada se detecta antes de publicar, no después.

## Fuera de alcance

- Formatos con conocimiento del lenguaje (claves JSON, tablas TOML). Se localiza la versión con una expresión regular, que sirve para cualquier formato.
- Versiones que no sean `X.Y.Z` (prerelease, metadatos de build).
- Ficheros fuera del repositorio.

## Comportamiento

### Configuración

Lista nueva `release.version_files` en `.claude/methodology.toml`, vacía por defecto:

```toml
[[release.version_files]]
path = "package.json"
pattern = '"version": "(\d+\.\d+\.\d+)"'
```

- `path` es una ruta relativa al repo, normalizada y sin `..`.
- `pattern` es una expresión regular con **exactamente un grupo de captura**, que es la versión.
- Cada entrada tiene solo esas dos claves. No puede haber dos entradas con el mismo `path` y el mismo `pattern`.
- Una entrada inválida es fail-fast al cargar la configuración: ningún comando se ejecuta.

### Publicación

`mth release` (después de sus gates y antes de crear la rama de release) y `mth hotfix finish` (antes de sus gates, para no pedir revisión de un hotfix que no podría publicarse) comprueban cada entrada. El fichero debe existir y el patrón debe aparecer **exactamente una vez**. Si alguna entrada falla, no se publica y no se modifica nada.

En el commit `chore(release): vX.Y.Z`, cada captura se sustituye por la versión nueva, sin tocar el resto del fichero. El cuerpo del commit lista los ficheros actualizados. Si la captura ya es la versión nueva (una publicación reanudada), el fichero no cambia.

### Diagnóstico

`mth doctor` muestra, por cada entrada, la versión que declara el fichero:

- ✓ si coincide con la última etiqueta de versión;
- ⚠ si no coincide, con las dos versiones;
- ✗ si el fichero no existe o el patrón no aparece exactamente una vez.

## Modos de fallo

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Entrada sin `path` o `pattern`, con claves de más, ruta absoluta o con `..`, regex inválida, sin grupo o con varios, o duplicada | Carga de la configuración | Fail-fast: ningún comando se ejecuta; el error nombra la entrada |
| El fichero no existe | `mth release`, `mth hotfix finish`, `mth doctor` | Publicación: error antes de crear rama o commit. Doctor: ✗ |
| El patrón no aparece o aparece más de una vez | `mth release`, `mth hotfix finish`, `mth doctor` | Lo mismo, indicando cuántas coincidencias hay |
| La versión declarada no coincide con la última etiqueta | `mth doctor` | ⚠ con las dos versiones; no bloquea, porque entre versiones es un aviso |

## Criterios de aceptación

- **AC-01**: Sin `release.version_files`, la configuración tiene una lista vacía y publicar no toca ningún fichero aparte del CHANGELOG.
- **AC-02**: La carga de la configuración rechaza una entrada sin `path` o sin `pattern`, con claves desconocidas, con ruta absoluta o con `..`, con una regex inválida o sin exactamente un grupo, y una entrada duplicada.
- **AC-03**: `mth release` sustituye la captura de cada fichero declarado por la versión nueva en el commit `chore(release)`, deja intacto el resto del fichero y lista los ficheros en el cuerpo del commit.
- **AC-04**: `mth hotfix finish` actualiza los ficheros declarados con la versión patch en su commit `chore(release)`.
- **AC-05**: Si un fichero declarado no existe o su patrón aparece cero o más de una vez, `mth release` falla antes de crear la rama de release y no modifica ningún fichero.
- **AC-06**: `mth doctor` marca con ✓ cada fichero cuya versión coincide con la última etiqueta, con ⚠ uno desfasado y con ✗ uno que no existe o cuyo patrón no aparece exactamente una vez.

## Notas

Este repo declara `plugins/methodology/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` y `plugins/methodology/scripts/mthlib/__init__.py`.
