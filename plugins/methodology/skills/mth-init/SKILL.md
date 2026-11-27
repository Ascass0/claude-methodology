---
name: mth-init
description: Adopta claude-methodology en un repo con una entrevista guiada, o diagnostica su adopción. Úsala si el contexto dice que el repo no ha adoptado la metodología, si piden prepararlo o configurarlo, o si algo falla (hook commit-msg, configuración inválida, gh sin autenticar).
model: opus
---

# Adoptar la metodología

`mth` es el comando del contexto de sesión (`$MTH`). La adopción la conduce Opus porque es la tarea con más criterio del ciclo: entender cómo trabaja ya el repo y adaptar la metodología sin romperlo. Lo determinista lo hace `mth`: el inventario, qué se deduce y qué se pregunta, y la traducción de respuestas a configuración.

Si el repo ya tiene `.claude/methodology.toml` y la persona quiere cambiar cómo se aplica la metodología o rehacer la entrevista, usa la skill `mth-reconfigure`.

## 1. Inventario

1. Árbol limpio y remoto con `main`. Si no, díselo a la persona y para.
2. `mth survey --json` (solo lee). Da el perfil (`new`, `existing`, `methodology`, `fork`), las señales y las preguntas del inventario, cada una con su `outcome`: `decision` (se pregunta), `deducida` o `por_defecto` (no se pregunta; llevan `answer` y `basis`), y, si el inventario restringe las opciones, `options`.
3. Lee lo que el inventario señala y no puedes juzgar sin leer: CLAUDE.md o AGENTS.md, las `description` de `.claude/agents/`, un par de specs o ADR de ejemplo y los hooks.

## 2. Presenta la metodología

Un mensaje breve antes de la primera pregunta:

> **claude-methodology** hace que Claude desarrolle de forma autónoma a partir de specs: cada cambio parte de una spec con criterios de aceptación, cada decisión estructural queda en un ADR, cada criterio tiene un test, y git se usa sin reescribir historia (ramas por tarea, commits convencionales, integración por PR). He analizado tu repo: {perfil y señales en una línea}. He resuelto yo {d} cosas a partir del repo y te haré {k} preguntas, solo sobre los puntos en los que tu forma de trabajar y la metodología difieren. Antes de escribir nada verás el plan completo, y nada se aplica hasta que revises el PR de adopción.

En un repo nuevo, sustituye la segunda mitad por: «El repo está vacío, así que solo necesito {k} preferencias.» `{k}` es el número de preguntas `decision`; `{d}`, el de las demás.

## 3. Pregunta

- Haz **solo** las preguntas con `outcome: decision`, con los textos de [preguntas.md](preguntas.md), en el orden del inventario (la precedencia entre el repo y la metodología va primero) y en una ronda con `AskUserQuestion` (un repo nuevo hace como mucho seis preguntas). Ofrece únicamente las opciones de `options` cuando el inventario las da.
- `AskUserQuestion` admite cuatro preguntas por ronda: con más de cuatro `decision` (un repo nuevo puede llegar a seis), hazlas en dos rondas. Si en un repo existente son demasiadas, avisa a la persona de que falta una regla de deducción: anótalo en tu mensaje de cierre.
- Las preguntas `deducida` y `por_defecto` no se preguntan: aparecen en el resumen del paso 4, donde la persona las corrige si quiere.
- Si la persona corrige el perfil o la evidencia ("esas RFC están abandonadas"), ajústalo en la respuesta que corresponda. El inventario no se edita.
- Si rechaza adoptar en cualquier momento: `mth init --decline` y termina.

### Perfil `methodology`: plan de migración

Tras la ronda de preguntas, presenta una tabla con cada artefacto afectado (carpetas de specs y ADR, agentes, hooks, líneas de CLAUDE.md, herramientas de publicación) y lo que se hará con él: mapear, convertir, archivar, encadenar o retirar. Pregunta con `AskUserQuestion` si la aprueba o qué quiere ajustar. Ajusta solo lo que señale y vuelve a preguntar. Si tras **tres rondas de ajuste** no hay acuerdo, detente, resume lo pendiente y no adoptes.

### Sin sesión interactiva

Si no puedes preguntar: con el perfil `new`, adopta con las opciones recomendadas; con cualquier otro, muestra el inventario y para.

## 4. Muestra el plan y adopta

1. Escribe las respuestas en un fichero del scratchpad (fuera del repo): `{"answers": {"<id>": {"option": "…", …}}}`. Solo hacen falta las de las preguntas `decision`; una respuesta a una pregunta `deducida` o `por_defecto` sustituye su valor.
2. `mth init --answers <fichero> --plan` valida las respuestas y **no escribe nada**: imprime el plan con lo deducido (con su evidencia), lo que va por defecto, lo decidido y las capacidades activas y desactivadas con su motivo. Preséntalo a la persona tal cual y pregunta con `AskUserQuestion` si lo confirma o qué valor quiere cambiar. Si cambia algo, añade esa respuesta al JSON y vuelve a ejecutar `--plan`. Si lo rechaza, no adoptes.
3. Con la confirmación: `mth init --answers <fichero> --marketplace-repo <owner>/claude-methodology --github`. Imprime el mismo plan, genera `methodology.toml` y el ADR de adopción (con el resultado de cada pregunta) y abre `chore/adopt-methodology` con un único commit. Si rechaza el JSON, corrige la respuesta que indique; no edites el inventario.
4. En la misma rama, y en commits `chore(methodology)` o `docs`, haz lo no determinista que pidieron las respuestas:
   - `convertir` / `archivar` specs o ADR;
   - retirar de CLAUDE.md las líneas contradictorias (`instrucciones: metodologia`);
   - renombrar los agentes que colisionan (`colision: renombrar`) y actualizar sus referencias;
   - crear el workflow de CI (`ci: crear`);
   - añadir `mth check-msg "$1"` al gestor de hooks, si lo hay;
   - rellenar la sección local (`<!-- mth:local:begin -->`) de los agentes del catálogo instalados: el modelo de amenazas de `revisor-seguridad` es obligatorio. Sale de lo que has leído del repo; si no hay base para escribirlo, pregunta a la persona.
   - secretos: la pregunta `secretos` (siempre `decision`) ofrece `bloquear` (`secrets.mode = "block"`, `secrets.hook = "on"` y, con GitHub y CI exigida, `secrets.ci = "on"`), `integrar` (`block` sin hook ni CI) y `ninguno` (todo `off`); requiere `gitleaks` ≥ 8.19.0, que la persona debe instalar. El workflow lo escribe `mth`, no tú. Con `block`, ejecuta `mth secrets --history`: lo que ya haya en el historial se rota y solo después se acepta con `--accept`. Recuerda que la protección de rama debe exigir la comprobación del workflow. Anota la decisión en el ADR de adopción;
5. `mth doctor` sin ✗ y `mth trace` sin errores (los avisos de legado son normales en una adopción gradual).
6. Integra con la skill `mth-integrate` (`--title "chore(methodology): adopt claude-methodology"`).

## 5. Cierra

Un mensaje final con tres listas: lo que se aplica tal cual, lo adaptado a este repo y dónde está registrado (el ADR de adopción y el PR). Incluye las capacidades que quedan desactivadas y por qué.

## Fork de otro proyecto

`mth survey` lo detecta por el remoto `upstream`, y `mth init --answers` fija `paths.claude_md = ".claude/CLAUDE.md"` y `commits.external_refs`. Lo demás se ajusta con respuestas `otro` en la pregunta que corresponda: `paths.*` bajo un directorio propio, `release.tag_prefix` propio y `trace.include` limitado a lo propio. Las sincronizaciones con upstream se hacen por merge en una rama `sync/`, nunca por cherry-pick, porque un cherry-pick crea commits nuevos que sí se validarían como propios.

## Agentes del catálogo después de adoptar

Se gestionan con `mth agents list | add | sync | diff | remove` en una rama `chore/`, no con la reestructuración.

## Diagnóstico

`mth doctor` lista cada comprobación con ✓, ✗ (bloquea) o ⚠ (aviso). Corrige los ✗ en una rama `chore/`.
