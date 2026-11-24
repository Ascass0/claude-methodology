---
name: mth-reconfigure
description: Repite la entrevista de adopción en un repo ya adoptado para reestructurar la metodología, revisar un bloque (flujo git, documentación, calidad, agente) o cambiar una decisión. Úsala si quieren cambiar autonomía, revisores, ramas, hooks, versiones, specs, idioma o modelos, en lugar de editar .claude/methodology.toml a mano.
model: opus
---

# Reestructurar la metodología

`mth` es el comando del contexto de sesión (`$MTH`). Es la misma entrevista que la adopción (skill `mth-init`), con el mismo catálogo de preguntas ([preguntas.md](../mth-init/preguntas.md)), pero sobre un repo que ya la ha adoptado. Las respuestas se aplican **sobre la configuración actual**: lo que no se pregunta no cambia (SPEC-0011 y ADR-0007 de claude-methodology).

Si el repo no tiene `.claude/methodology.toml`, esta skill no aplica: usa `mth-init`.

## 1. Alcance

1. Árbol limpio y sin una rama `chore/reconfigure-methodology` abierta. Si no, díselo a la persona y para.
2. Pregunta con `AskUserQuestion` qué quiere revisar:
   - **Formulario completo**: todas las preguntas aplicables.
   - **Por bloques**: después, una pregunta `multiSelect` con los bloques.
   - **Un cambio concreto**: la persona lo describe con sus palabras (opción "Otro"). Tradúcelo a IDs de pregunta y confírmalo antes de seguir.

| Bloque | Preguntas | Qué decide |
|---|---|---|
| `flujo` | `forja`, `ramas`, `commits`, `versiones`, `ci` | forja del remoto, rama de integración, hook `commit-msg`, publicación y CI |
| `documentacion` | `alcance`, `specs`, `decisiones`, `idioma`, `instrucciones` | legado, specs, ADR, idioma y CLAUDE.md |
| `calidad` | `tests`, `revisores`, `colision` | comando de tests y revisores |
| `agente` | `autonomia`, `modelos` | cuánto pregunta Claude y con qué modelos trabaja |

## 2. Inventario

`mth survey --reconfigure --json` (con `--only <bloques o IDs>` si no es el formulario completo). Solo lee. Da cada pregunta aplicable con su `evidence` y su `current`, que es el valor actual. Guarda el `--only` exacto: `mth reconfigure` lo necesita igual.

Antes de la primera pregunta, un mensaje breve: qué se va a revisar, que nada se aplica hasta el PR y que lo que no se pregunte se conserva.

## 3. Pregunta

- Haz las preguntas del inventario con los textos de [preguntas.md](../mth-init/preguntas.md), en su orden y en rondas de hasta cuatro con `AskUserQuestion`.
- Empieza cada pregunta con `Ahora: {current}.` y añade ` (actual)` a la etiqueta de la opción que corresponde a lo que hay. La opción recomendada sigue siendo la primera.
- Las frases del catálogo que hablan de la adopción («tu repo tiene…») se adaptan al presente del repo; las opciones y sus respuestas JSON no cambian.
- Diferencias con la adopción:
  - `revisores`: la lista que des es la lista completa (incluye `verificador` si se mantiene). Incluye también los revisores del catálogo instalados (`mth agents list`), en el orden en que están. `catalog` y `vars` no se admiten aquí: los agentes del catálogo se instalan y retiran con `mth agents`.
  - `alcance: gradual` conserva el `trace.legacy_base` que haya; `completa` lo vacía y todo el contenido pasa a cumplir las reglas.
  - `versiones: continuar` conserva la numeración; pasa `version_files` solo si cambian.
- Cambiar `ramas` o las rutas de `specs`/`decisiones` afecta a las ramas abiertas: díselo a la persona antes de aplicarlo.

### Plan de migración

Si alguna respuesta pide trabajo además de la configuración (`specs`/`decisiones` con `convertir` o `archivar`, `colision: renombrar`, `instrucciones: metodologia`, `ci: crear`), presenta una tabla con cada artefacto afectado y lo que se hará con él, y pregunta si la aprueba. Ajusta solo lo que señale. Si tras **tres rondas de ajuste** no hay acuerdo, detente y no apliques nada.

## 4. Aplica

1. Escribe las respuestas en `.work/plans/reconfigure-answers.json`: `{"answers": {"<id>": {"option": "…", …}}}`.
2. `mth reconfigure --answers .work/plans/reconfigure-answers.json [--only <lo mismo que en el inventario>]`. Valida todo antes de tocar nada. Después abre `chore/reconfigure-methodology` con la configuración y el ADR de reestructuración en un único commit. Si rechaza las respuestas, corrige la que indique. Si dice «nada que cambiar», díselo a la persona y termina.
3. En la misma rama, en commits `chore(methodology)` o `docs`, haz las migraciones pendientes que lista el comando, igual que en la adopción.
4. `mth doctor` sin ✗ y `mth trace` sin errores.
5. Integra con la skill `mth-integrate` (`--title "chore(methodology): reconfigure claude-methodology"`).

## 5. Cierra

Un mensaje final con lo que cambió (clave: antes → después), las migraciones hechas y dónde quedó registrado (el ADR de reestructuración y el PR). El fichero de configuración se regenera, así que sus comentarios se pierden: el porqué de cada cambio queda en el ADR.
