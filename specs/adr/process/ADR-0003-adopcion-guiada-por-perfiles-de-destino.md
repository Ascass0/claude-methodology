# ADR-0003 · Adopción guiada por perfiles de destino

- Estado: aceptado
- Fecha: 2026-11-18
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

`mth init` adopta la metodología añadiendo ficheros. No detecta la forma de trabajar que ya tenga el repo y deja a criterio de Claude cómo ajustar la configuración. En un repo avanzado esto produce conflictos silenciosos: specs en otra carpeta que dejan de estar trazadas, un hook `commit-msg` ajeno que desactiva la validación, agentes del repo que sustituyen a los del plugin, instrucciones de CLAUDE.md que contradicen las reglas base o una rama `development` que nadie usa.

Además, el plugin se activa antes de adoptar. Si está instalado a nivel de usuario, el hook de sesión inyecta las reglas base y el guard bloquea `main` en todos los repos de esa persona, también en los que nunca decidió adoptarlo.

Fuerzas en juego:

- **Instalar no es aceptarlo todo.** Quien instala el plugin quiere llegar a la metodología, no perder lo que ya tiene.
- **Cada destino necesita una conversación distinta.** Un repo vacío no tiene nada que proteger; uno con metodología propia necesita decidir artefacto por artefacto.
- **Determinismo** (PRINCIPLES §2): detectar qué hay en el repo y traducir respuestas a configuración son operaciones deterministas. Interpretar instrucciones en prosa o convertir documentos no lo son.
- **Trazabilidad:** las adaptaciones de la metodología a un repo son decisiones estructurales de ese repo.

## Decisión

1. **El plugin no actúa hasta que el repo adopta.** Sin `.claude/methodology.toml`, el hook de sesión no inyecta las reglas base, sino una instrucción breve para proponer la adopción guiada en la primera respuesta, y el guard no bloquea nada. Quien la rechaza la desactiva para ese repo en `.claude/settings.local.json`, que no se versiona.
2. **El inventario es determinista.** `mth survey` detecta señales del repo, lo clasifica en un perfil (nuevo, existente, con metodología propia, fork) y decide qué preguntas hacen falta: las de la base del perfil más las que dispara cada conflicto detectado.
3. **La entrevista la conduce Opus.** La skill `mth-init` se ejecuta con `model: opus`, porque es la tarea con más criterio del ciclo y se ejecuta antes de que exista `[models]`. Los textos de cada pregunta son fijos y están en la skill, para que la metodología se presente siempre igual. Opus solo rellena lo detectado, omite lo que no aplica e itera sobre el plan de migración en el perfil con metodología propia.
4. **Las respuestas se traducen a configuración con código.** Opus escribe las respuestas en un JSON y `mth init --answers` lo valida contra el inventario, genera `methodology.toml` y el ADR de adopción del repo destino, y abre la rama de adopción. Una respuesta personalizada ("Otro") se expresa como claves de configuración que se validan igual que el resto.
5. **Lo que no es determinista lo hace Opus en la rama de adopción**: convertir documentos, retirar líneas de CLAUDE.md, renombrar agentes o crear un workflow de CI. Todo queda en el PR de adopción.
6. **Sin respuestas no se migra.** Sin sesión interactiva, el perfil nuevo puede adoptarse con los valores por defecto. Los demás perfiles se detienen tras el inventario.

## Alternativas consideradas

- **Migración automática completa:** convertir specs, hooks y agentes sin preguntar. Decide por la persona y produce un PR enorme e imposible de revisar.
- **Un cuestionario fijo para todos los repos:** catorce preguntas en un repo vacío ahuyentan a quien empieza, y en un repo con metodología propia no bastan.
- **Que Opus genere directamente `methodology.toml`:** funcionaría casi siempre, pero un error de configuración solo aparecería después. Con el JSON de respuestas, la traducción es determinista y está probada.
- **Bloquear la sesión hasta adoptar:** un hook no puede impedir que la persona trabaje, y no debería hacerlo en un repo que no ha decidido nada.

## Consecuencias

- **Positivas:** el plugin se puede instalar a nivel de usuario sin efectos en los repos que no lo adoptan. La adopción hace solo las preguntas necesarias, y cada adaptación queda registrada en el ADR de adopción del repo.
- **Negativas:** hay que mantener la coherencia entre las preguntas del inventario y los textos de la skill (un test lo comprueba). La adopción de un repo con metodología propia cuesta una sesión de Opus.
- **Riesgo aceptado:** la detección de señales es heurística (nombres de carpetas, ficheros conocidos). Lo que no detecta no genera pregunta, pero Opus revisa el inventario y la persona puede corregir el perfil en la primera pregunta.
