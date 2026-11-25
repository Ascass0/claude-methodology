# SPEC-0007 · Autonomía configurable

- Estado: implementada
- Fecha: 2026-11-18
- Formato: compacto
- ADRs: ADR-0004
- Sustituye a: —


## Contexto

- La metodología trabaja con autonomía completa; PRINCIPLES §11 deja la supervisión a un hook propio de cada repo.
- Al adoptar en un repo con equipo o revisión manual, la autonomía es el cambio más fuerte: la adopción guiada ([SPEC-0004](SPEC-0004-adopcion-guiada.md)) debe ofrecer niveles intermedios sin que cada repo programe un hook.
- Decisión: [ADR-0004](../adr/process/ADR-0004-autonomia-configurable-por-repositorio.md).

## Objetivo

El repo elige entre tres niveles de autonomía. El guard pide confirmación a la persona antes de los pasos que su nivel reserva, y las reglas de sesión describen ese nivel.

## Fuera de alcance

- Confirmaciones por tipo de rama o por ruta.
- Confirmar acciones que no pasan por la herramienta Bash.

## Comportamiento

Tabla nueva `[autonomy]`, con la clave `level`:

| Nivel | Pide confirmación antes de |
|---|---|
| `full` (por defecto) | nada |
| `until-pr` | `mth integrate`, `mth release`, `mth hotfix finish` |
| `supervised` | lo anterior, más `mth commit`, `mth branch`, `git commit` y `git push` |

- **Guard.** Para un comando que su nivel reserva, el guard no bloquea: responde a Claude Code con la decisión `ask` y el motivo, y Claude Code pide confirmación a la persona. Reconoce `mth` escrito como `$MTH`, `${MTH}`, una ruta que termina en `/mth` o `mth.py`, o `mth` a secas, también precedido de `sh` o de un intérprete de Python. Un comando que el guard bloquea sigue bloqueado: el bloqueo tiene prioridad sobre la confirmación.
- **Sin sesión interactiva**, Claude Code trata `ask` como denegación. Es el estado seguro.
- **Reglas de sesión.** El párrafo de autonomía de las reglas base cambia según el nivel e indica qué pasos se confirman.
- **PRINCIPLES §11** pasa a describir los tres niveles. La autonomía completa sigue siendo el valor por defecto.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | Nivel desconocido | Fail-fast al cargar; el guard, que no puede cargar, aplica `supervised` en vez de dejar pasar | AC-06 |
| FM-02 | La persona rechaza la confirmación | El comando no se ejecuta; Claude lo trata como rechazo y no lo reintenta por otra vía | AC-02 |
| FM-03 | Sesión no interactiva | `ask` equivale a denegar | AC-02 |

## Criterios de aceptación

- **AC-01**: MIENTRAS `level = "full"` o no exista la tabla, el guard NO DEBE pedir confirmación para ningún comando.
- **AC-02**: MIENTRAS `level = "until-pr"`, el guard DEBE responder `ask` para `mth integrate`, `mth release` y `mth hotfix finish` con cualquier forma de invocar `mth`, y NO DEBE hacerlo para `mth commit` ni `mth branch`.
- **AC-03**: MIENTRAS `level = "supervised"`, el guard DEBE responder `ask` además para `mth commit`, `mth branch`, `git commit` y `git push`.
- **AC-04**: SI el guard bloquea un comando (p. ej. `git push --force`), ENTONCES DEBE bloquearlo igual en cualquier nivel, sin pedir confirmación.
- **AC-05**: Las reglas de sesión DEBEN describir el nivel configurado y los pasos que se confirman.
- **AC-06**: SI el nivel no es `full`, `until-pr` o `supervised`, ENTONCES la carga de la configuración DEBE rechazarlo; SI la configuración es inválida, ENTONCES el guard DEBE pedir confirmación como en `supervised`.

## Notas

—
