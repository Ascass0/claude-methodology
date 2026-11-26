# SPEC-0003 · Ficheros de versión en la publicación

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: —
- Sustituye a: —


## Contexto

- `mth release` y `mth hotfix finish` calculan la versión, crean la etiqueta y actualizan el CHANGELOG, pero no tocan los ficheros donde el proyecto declara su versión (`package.json`, `pyproject.toml`; en este repo `plugin.json`, `marketplace.json` y `mthlib/__init__.py`); se actualizaban a mano.
- En la 0.5.0 nadie lo hizo: se publicó declarando 0.4.0 y, como Claude Code actualiza plugins por versión, quien ya lo tenía no recibió la actualización.
- La v0.5.1 corrigió los ficheros pero no la causa.

## Objetivo

1. El repo declara en su configuración qué ficheros contienen la versión y dónde.
2. Publicar una versión (normal o hotfix) los actualiza en el mismo commit que el CHANGELOG.
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

`mth release` (después de sus gates y antes de crear la rama de release) y `mth hotfix finish` (antes de sus gates, para no pedir revisión de un hotfix que no podría publicarse) comprueban cada entrada. El fichero debe existir, el patrón debe aparecer **exactamente una vez** y su grupo de captura debe participar en la coincidencia (un grupo opcional que no captura nada no dice dónde va la versión). Si alguna entrada falla, no se publica y no se modifica nada.

En el commit `chore(release): vX.Y.Z`, cada captura se sustituye por la versión nueva, sin tocar el resto del fichero: ni el contenido ni los finales de línea (un fichero con CRLF sigue teniendo CRLF). El cuerpo del commit lista los ficheros actualizados. Si la captura ya es la versión nueva (una publicación reanudada), el fichero no cambia.

### Diagnóstico

`mth doctor` muestra, por cada entrada, la versión que declara el fichero:

- ✓ si coincide con la última etiqueta de versión;
- ⚠ si no coincide, con las dos versiones;
- ✗ si el fichero no existe o el patrón no aparece exactamente una vez.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Entrada sin `path` o `pattern`, con claves de más, ruta absoluta o con `..`, regex inválida, sin grupo o con varios, o duplicada | Fail-fast al cargar la configuración: ningún comando se ejecuta; el error nombra la entrada | AC-02 |
| FM-02 | El fichero no existe | Publicación: error antes de crear rama o commit. Doctor: ✗ | AC-05, AC-06 |
| FM-03 | El patrón no aparece o aparece más de una vez | Lo mismo, indicando cuántas coincidencias hay | AC-05, AC-06 |
| FM-04 | El grupo de captura es opcional y no participa en la coincidencia | Como un patrón que no aparece: error antes de modificar nada; doctor: ✗ | AC-08 |
| FM-05 | La versión declarada no coincide con la última etiqueta | `mth doctor`: ⚠ con las dos versiones; no bloquea (entre versiones es un aviso) | AC-06 |

## Criterios de aceptación

- **AC-01**: MIENTRAS no se declare `release.version_files`, la configuración DEBE tener una lista vacía y publicar NO DEBE tocar ningún fichero aparte del CHANGELOG.
- **AC-02**: SI una entrada de `release.version_files` carece de `path` o `pattern`, tiene claves desconocidas, ruta absoluta o con `..`, una regex inválida o sin exactamente un grupo, o está duplicada, ENTONCES la carga de la configuración DEBE rechazarla.
- **AC-03**: CUANDO se ejecuta `mth release`, `mth` DEBE sustituir la captura de cada fichero declarado por la versión nueva en el commit `chore(release)`, dejar intacto el resto y listar los ficheros en el cuerpo del commit.
- **AC-04**: CUANDO se ejecuta `mth hotfix finish`, `mth` DEBE actualizar los ficheros declarados con la versión patch en su commit `chore(release)`.
- **AC-05**: SI un fichero declarado no existe o su patrón aparece cero o más de una vez, ENTONCES `mth release` DEBE fallar antes de crear la rama de release sin modificar ningún fichero.
- **AC-06**: CUANDO se ejecuta `mth doctor`, `mth` DEBE marcar con ✓ cada fichero cuya versión coincide con la última etiqueta, con ⚠ uno desfasado y con ✗ uno inexistente o cuyo patrón no aparece exactamente una vez.
- **AC-07**: CUANDO se sustituye la versión, `mth` DEBE conservar el resto del fichero byte a byte, incluidos los finales de línea CRLF.
- **AC-08**: SI el grupo de captura no participa en la coincidencia, ENTONCES leer o escribir los ficheros de versión DEBE fallar sin modificar ninguno.

## Notas

Este repo declara `plugins/methodology/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` y `plugins/methodology/scripts/mthlib/__init__.py`.
