---
name: mth-review
description: Ejecuta la revisión de la rama con los agentes revisores del repo (contexto limpio, severidades, precedencia) y la registra sobre el HEAD exacto. Úsala antes de integrar una rama feat, fix o hotfix y tras cada commit nuevo posterior a una revisión.
---

# Revisión

`mth` es el comando del contexto de sesión (`$MTH`). Los revisores son `review.agents` en `.claude/methodology.toml`, en orden de precedencia. Algunos solo aplican si el diff toca sus rutas (`review.paths`): **`mth review status` dice cuáles son obligatorios para esta rama**. Lanza esos y ninguno más.

`verificador` (compartido, incluido en el plugin) comprueba que la rama cumple su spec y ejecuta los tests. Si está en la lista, va primero: no tiene sentido revisar estilo o parsimonia de algo que no cumple la spec.

Los revisores del catálogo (`revisor-seguridad`, `revisor-fallos`, `revisor-adr`, `revisor-diseno`, `revisor-parsimonia`) se instalan en `.claude/agents/` con `mth agents add`, que los coloca en `review.agents` según la precedencia de PRINCIPLES §0. Su guard solo les deja leer git: no les pidas otra cosa.

## Antes de revisar

1. `mth sync` (la revisión es sobre el HEAD que se va a integrar).
2. Lo determinista primero: tests, `commands.precommit`, `mth trace`. Un agente no revisa lo que una herramienta comprueba.

## Revisar

Lanza los revisores obligatorios **en el orden de `review.agents`**: el `verificador` primero y, si no hay bloqueantes, el resto como subagentes (herramienta Agent con su nombre y el modelo `models.review` que muestra `mth models`; los del plugin pueden aparecer con el prefijo `methodology:`), en paralelo si es posible. A cada uno, este encargo y nada más (contexto limpio: ni la conversación ni tu razonamiento):

```
Revisa la rama <rama> respecto a <destino>.
- Diff: git diff <remoto>/<destino>...HEAD
- Specs y ADR afectados: <IDs y rutas>
- Plan acordado (solo al verificador): <ruta de .work/plans/PLAN-NNNN-*.md de la rama, `mth plan list`>; avisa si el diff se sale del plan
- Principios: <ruta de PRINCIPLES.md del contexto de sesión>
Aplica solo tu especialidad. Para cada hallazgo devuelve:
  severidad (bloqueante | importante | sugerencia) · fichero:línea · problema · corrección propuesta
Bloqueante = incumple una regla DEBE, un criterio de aceptación, o introduce un riesgo.
No inventes títulos de sección: solo FUERA DE ALCANCE, RESUMEN:, BLOQUEANTES:, TESTS:, CRITERIOS y ALCANCE: además de HALLAZGOS.
Termina con: BLOQUEANTES: <n>
```

Títulos de sección que `mth` admite en un informe: `FUERA DE ALCANCE`, `RESUMEN:`, `BLOQUEANTES:`, `TESTS:`, `CRITERIOS` y `ALCANCE:`. Cualquier otro título dentro de `HALLAZGOS` hace fallar el registro: no inventes títulos y pide a los revisores que no los usen.

Guarda el informe de cada revisor **tal cual lo devolvió**, sin resumir ni retocar, en `.work/tmp/<agente>.md` (`mth` solo lee informes dentro del repo). `mth review record` lo archiva byte a byte en `.work/reviews/<sha>-<agente>-<n>.md` (`<n>` = número de intento) y es el registro de la revisión. Si quieres un resumen, que sea un fichero aparte que enlace al original; nunca lo sustituye. El informe incluye siempre la sección `HALLAZGOS` y termina con `BLOQUEANTES: <n>`.

**El número de bloqueantes lo calcula `mth`:** cuenta las líneas `N. [bloqueante] …` de `HALLAZGOS` y contrasta la línea `BLOQUEANTES: <n>` del agente. Si no coinciden, o `mth` no sabe leer el formato (sección ausente, viñetas, texto suelto, severidad desconocida, informe vacío o ausente), registra la revisión como **fallida**: no aprueba nada y `mth review status` la muestra con su motivo y su número de intento.

**Revisor que falla** (informe ilegible o incoherente, se cae o agota el tiempo): no ha revisado. Nunca cuenta como "sin hallazgos".
- Primer fallo: pide **una** corrección al **mismo** agente con `SendMessage` (mismo contexto), citando el motivo que imprime `mth`, y registra de nuevo. No lances otro agente desde cero: eso es volver a tirar el dado.
- Segundo fallo: detente y avisa (PRINCIPLES §11). El fallo está en el prompt del revisor; `attempts` y `reason` del registro lo dejan ver.
- Si el agente no puede continuar (sin contexto, caído), relánzalo una vez con el mismo encargo y cuéntalo como el segundo intento.

## Resolver

- Corrige los bloqueantes. Los importantes, salvo que contradigan una regla de mayor precedencia (seguridad > fail-safe/fail-fast > corrección > trazabilidad > parsimonia > estilo); las sugerencias, a criterio.
- Si dos revisores se contradicen, gana la precedencia; entre revisores, el que va antes en `review.agents`. Anota la decisión en el resumen.
- Tras corregir: commit (skill `mth-commit`) y **vuelve a revisar**: un commit nuevo invalida las revisiones anteriores.

## Registrar

Por cada agente, sobre el HEAD final:

```
mth review record <agente> --report <informe> --summary "<resumen en español en una línea>"
mth review status
```

`mth` calcula los bloqueantes del informe. Si falta, está vacío o no se puede leer, o la cuenta no coincide con la que declara el revisor, registra la revisión como fallida y la integración sigue bloqueada.

`mth integrate` exige un registro con 0 bloqueantes de cada revisor para el HEAD actual, y copia los resúmenes al PR.
