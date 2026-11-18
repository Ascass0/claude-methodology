# SPEC-0007 · Autonomía configurable

- Estado: aprobada
- Fecha: 2026-11-18
- ADRs: ADR-0004
- Sustituye a: —

<!-- Estados: borrador → aprobada → implementada → sustituida.
     "implementada" exige que cada AC tenga un test con `verifies: SPEC-0007/AC-NN`. -->

## Contexto

La metodología trabaja con autonomía completa: Claude crea ramas, hace commits, integra y publica sin pedir permiso. PRINCIPLES §11 deja la supervisión en manos de cada repo, que tendría que escribir su propio hook. En la adopción de un repo con equipo o con hábitos de revisión manual, la autonomía es el cambio más fuerte, y la adopción guiada ([SPEC-0004](SPEC-0004-adopcion-guiada.md)) tiene que poder ofrecer niveles intermedios sin que cada repo programe un hook. [ADR-0004](../adr/process/ADR-0004-autonomia-configurable-por-repositorio.md) recoge la decisión.

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

| Fallo | Detección | Respuesta (estado seguro) |
|---|---|---|
| Nivel desconocido | Carga de la configuración | Fail-fast. El guard, que no puede cargar la configuración, aplica `supervised` en vez de dejar pasar sin confirmar |
| La persona rechaza la confirmación | Claude Code | El comando no se ejecuta; Claude lo trata como un rechazo y no lo reintenta por otra vía |
| Sesión no interactiva | Claude Code | `ask` equivale a denegar |

## Criterios de aceptación

- **AC-01**: Con `level = "full"` o sin la tabla, el guard no pide confirmación para ningún comando.
- **AC-02**: Con `until-pr`, el guard responde `ask` para `mth integrate`, `mth release` y `mth hotfix finish`, con cualquiera de las formas de invocar `mth`, y no para `mth commit` ni `mth branch`.
- **AC-03**: Con `supervised`, el guard responde `ask` además para `mth commit`, `mth branch`, `git commit` y `git push`.
- **AC-04**: Un comando que el guard bloquea (por ejemplo, un `git push --force`) se bloquea igual en cualquier nivel, sin pedir confirmación.
- **AC-05**: Las reglas de sesión describen el nivel configurado y los pasos que se confirman.
- **AC-06**: La carga de la configuración rechaza un nivel distinto de `full`, `until-pr` o `supervised`, y con una configuración inválida el guard pide confirmación como en `supervised`.

## Notas

—
