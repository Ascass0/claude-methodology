# SPEC-0009 · Actualización del plugin con configuración más nueva

- Estado: implementada
- Fecha: 2026-11-18
- ADRs: —
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0009/AC-NN`. -->

## Contexto

Cada versión del plugin añade claves a `.claude/methodology.toml` (la 0.6.0 añade `language`, `hooks`, `autonomy`, `trace.legacy_base` y `release.version_files`). Una clave que el plugin no conoce hace fallar la carga de la configuración. Es el comportamiento correcto: si un plugin antiguo ignorase `autonomy.level = "supervised"`, trabajaría sin supervisión.

El fallo se ve en los equipos mixtos. Si alguien añade una clave nueva a la configuración, quien sigue con la versión anterior se queda bloqueado: su hook `commit-msg` rechaza todos los commits y ningún comando `mth` arranca. El error dice "Revisa la ortografía", cuando la solución es actualizar el plugin y abrir una sesión nueva. Tampoco hay ningún sitio que explique cómo se actualiza.

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

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| La configuración usa una clave de una versión posterior del plugin | Carga de la configuración | Fail-fast, como hasta ahora: nada se ejecuta y el error dice qué versión la rechaza y cómo actualizar |
| `mth doctor` con configuración inválida | `mth doctor` | ✗ con el mensaje y la pista |

## Criterios de aceptación

- **AC-01**: El error de una clave desconocida, de primer nivel o anidada, nombra la clave y la versión del plugin, y su pista indica actualizar el plugin y abrir una sesión nueva.
- **AC-02**: Una configuración que solo usa claves de la 0.5.x se carga con `language.docs = "es"`, `hooks.commit_msg = "own"`, `autonomy.level = "full"`, `trace.legacy_base = ""` y `release.version_files = []`.
- **AC-03**: `mth doctor` con una configuración inválida muestra el mensaje y la pista del error.

## Notas

Se detectó al validar la 0.6.0: en este mismo repo, el plugin instalado (0.5.1) rechaza `release.version_files` y no puede publicar.
