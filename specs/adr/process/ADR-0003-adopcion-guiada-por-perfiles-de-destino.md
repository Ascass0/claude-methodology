# ADR-0003 · Adopción guiada por perfiles de destino

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process
- Formato: compacto

## Contexto

- `mth init` solo añadía ficheros: no detectaba cómo trabaja ya el repo y dejaba a criterio de Claude el ajuste. En un repo avanzado produce conflictos silenciosos: specs en otra carpeta sin trazar, un `commit-msg` ajeno que desactiva la validación, agentes propios que sustituyen a los del plugin, CLAUDE.md contradictorio o una `development` que nadie usa.
- El plugin se activa antes de adoptar: instalado a nivel de usuario, inyecta las reglas y el guard bloquea `main` también en repos que nunca decidieron adoptarlo.
- Instalar no es aceptarlo todo; cada destino pide una conversación distinta (vacío frente a metodología propia).
- Determinismo (PRINCIPLES §2): detectar el repo y traducir respuestas a configuración es determinista; interpretar prosa o convertir documentos no.
- Las adaptaciones de la metodología a un repo son decisiones estructurales de ese repo.

## Decisión

1. Sin `.claude/methodology.toml`, el hook de sesión NO DEBE inyectar las reglas base (solo una instrucción breve para proponer la adopción) y el guard NO DEBE bloquear nada. Quien rechaza adoptar lo desactiva en `.claude/settings.local.json` (no versionado).
2. `mth survey` DEBE ser determinista: detecta señales, clasifica el perfil (nuevo, existente, con metodología propia, fork) y decide las preguntas (base del perfil más las que dispara cada conflicto).
3. La entrevista la conduce Opus (`mth-init`, `model: opus`): es la tarea con más criterio y corre antes de que exista `[models]`. Los textos de las preguntas son fijos, en la skill. Opus solo rellena lo detectado, omite lo que no aplica e itera el plan de migración del perfil con metodología propia.
4. `mth init --answers` DEBE validar el JSON de respuestas contra el inventario, generar `methodology.toml` y el ADR de adopción del destino y abrir la rama de adopción. Una respuesta «Otro» se expresa como claves de configuración validadas igual.
5. Lo no determinista (convertir documentos, retirar líneas de CLAUDE.md, renombrar agentes, crear el workflow de CI) lo hace Opus en la rama de adopción; todo queda en el PR.
6. Sin respuestas NO DEBE migrarse: sin sesión interactiva, el perfil nuevo adopta los valores por defecto y los demás se detienen tras el inventario.

## Rechazado

- Migración automática completa: decide por la persona y produce un PR enorme e irrevisable.
- Cuestionario fijo: catorce preguntas ahuyentan en un repo vacío y no bastan con metodología propia.
- Que Opus genere `methodology.toml` directamente: un error de configuración aparecería tarde; con el JSON la traducción es determinista y está probada.
- Bloquear la sesión hasta adoptar: un hook no puede impedir trabajar y no debe hacerlo en un repo sin decisión.

## Consecuencias

- **+** El plugin se instala a nivel de usuario sin efectos en repos que no adoptan; solo se hacen las preguntas necesarias y cada adaptación queda en el ADR de adopción.
- **−** Hay que mantener la coherencia entre las preguntas del inventario y los textos de la skill (lo comprueba un test).
- **−** Adoptar un repo con metodología propia cuesta una sesión de Opus.
- **riesgo** La detección es heurística (nombres de carpetas, ficheros conocidos) → Opus revisa el inventario y la persona corrige el perfil en la primera pregunta.

## Impone

- [script] `mthlib/survey.py` (inventario y perfil), `mthlib/adoption.py` (traducción de respuestas), `mthlib/session.py` y `mthlib/guard.py` (inactivos sin configuración).
- [criterio] Test de coherencia entre las preguntas del inventario y `skills/mth-init/preguntas.md`.
