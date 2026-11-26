# SPEC-0009 · Actualización del plugin con configuración más nueva

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: —
- Sustituye a: —


## Contexto

- Cada versión del plugin añade claves a `.claude/methodology.toml` (la 0.6.0: `language`, `hooks`, `autonomy`, `trace.legacy_base`, `release.version_files`). Una clave desconocida hace fallar la carga: correcto, porque un plugin antiguo que ignorase `autonomy.level = "supervised"` trabajaría sin supervisión.
- En equipos mixtos, quien conserva la versión anterior queda bloqueado: su `commit-msg` rechaza todos los commits y ningún `mth` arranca.
- El error decía «Revisa la ortografía» cuando la solución es actualizar el plugin y abrir una sesión nueva; y no había dónde se explicara la actualización.

## Objetivo

1. Quien tenga el plugin desfasado sabe, por el error, qué versión tiene y qué debe hacer.
2. Actualizar el plugin en un repo ya adoptado no exige cambios en su configuración.
3. El README explica el orden seguro de actualización en un equipo.

## Fuera de alcance

- Aceptar o ignorar claves desconocidas: seguiría siendo inseguro (fail-safe > parsimonia).
- Una clave de versión mínima del plugin: el error de clave desconocida ya detecta el desfase en el momento en que importa.
- Corregir el mensaje de versiones ya publicadas.

## Comportamiento

- El error de clave desconocida nombra la clave y la versión del plugin que la rechaza: `Clave desconocida en la configuración: 'autonomy' (claude-methodology 0.6.0 no la reconoce).` La pista dice que, si no es una errata, la clave es de una versión posterior: hay que actualizar el plugin (`/plugin`) y abrir una sesión nueva de Claude Code.
- La pista llega a todos los sitios donde aparece el error: comandos `mth`, hook `commit-msg` (`mth check-msg`), estado del hook de sesión y `mth doctor`, que hasta ahora mostraba solo el mensaje de un error de configuración.
- Una configuración sin ninguna de las claves que añadió la 0.6.0 se carga con valores por defecto que mantienen el comportamiento anterior: `language.docs = "es"`, `hooks.commit_msg = "own"`, `autonomy.level = "full"`, `trace.legacy_base = ""` y `release.version_files = []`.
- El README tiene una sección "Actualizar el plugin" con el orden seguro (primero todo el equipo, después las claves nuevas en un PR), qué pasa con el trabajo a medias y con el hook `commit-msg`, y por qué hace falta una sesión nueva.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | La configuración usa una clave de una versión posterior | Fail-fast: nada se ejecuta; el error dice qué versión la rechaza y cómo actualizar | AC-01 |
| FM-02 | `mth doctor` con configuración inválida | ✗ con el mensaje y la pista | AC-03 |

## Criterios de aceptación

- **AC-01**: SI la configuración tiene una clave desconocida (de primer nivel o anidada), ENTONCES el error DEBE nombrar la clave y la versión del plugin, y su pista DEBE indicar actualizar el plugin y abrir una sesión nueva.
- **AC-02**: CUANDO una configuración solo usa claves de la 0.5.x, `mth` DEBE cargarla con `language.docs = "es"`, `hooks.commit_msg = "own"`, `autonomy.level = "full"`, `trace.legacy_base = ""` y `release.version_files = []`.
- **AC-03**: SI la configuración es inválida, ENTONCES `mth doctor` DEBE mostrar el mensaje y la pista del error.

## Notas

Se detectó al validar la 0.6.0: en este mismo repo, el plugin instalado (0.5.1) rechaza `release.version_files` y no puede publicar.
