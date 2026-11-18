# claude-methodology · reglas base

{{AUTONOMY}}

**Precedencia ante conflicto:** seguridad > fail-safe/fail-fast > corrección > trazabilidad > parsimonia > estilo.

**Ciclo:** rama (`mth-branch`) → spec y ADR en la rama (`mth-spec`) → implementación + tests + docs → commits temáticos (`mth-commit`) → revisión (`mth-review`) → integración (`mth-integrate`) → versión (`mth-release`). Visión completa: skill `mth-develop`.

**Reglas que no se negocian:**
- Ninguna operación de git que integre, etiquete o borre ramas se hace a mano: siempre con `mth` (`{{MTH}}`). Nunca se reescribe historia compartida (sin rebase, squash ni force-push).
- Sin spec no hay feature. Si la spec no existe, la escribes primero. Una decisión estructural sin ADR es un error.
- Cada criterio de aceptación tiene al menos un test (`verifies: SPEC-NNNN/AC-NN`). Cada modo de fallo diseñado, también.
- Excepciones: captura específica donde puedas actuar; captura genérica solo en los límites del sistema; nunca se traga un error; se encadena la causa.
- Diseño según SOLID (responsabilidad única; extensión sin modificar solo con variantes reales; implementaciones sustituibles; interfaces pequeñas; el dominio define sus abstracciones y la infraestructura las implementa) y sin antipatrones STUPID: dependencias explícitas en lugar de estado global, contratos estrechos, lógica separada de la E/S (tests unitarios sin infraestructura real), sin optimizar sin medir, nombres que revelan intención y cada conocimiento en un único sitio.
- Código y commits en inglés; docs, specs, changelog y PR en {{DOCS_LANGUAGE}} (`language.docs`).
- Los revisores del repo trabajan con contexto limpio (solo diff + specs + principios).
- Tus artefactos de trabajo van a `.work/` (local, excluido de git; nunca se versiona): `plans/` planes, manifiestos y borradores de diseño; `merge-request/` títulos y cuerpos de PR; `security-report/` informes de seguridad; `reviews/` informes de los revisores; `notes/` notas que se conservan entre sesiones; `tmp/` temporales desechables{{WORK_EXTRA}}. Nada de eso va al repo ni al scratchpad.

**Te detienes y avisas solo si:** dos specs o principios se contradicen y la precedencia no lo resuelve; un gate falla tres veces seguidas por la misma causa; o la tarea exige algo fuera de las specs con impacto irreversible (borrar datos, publicar fuera del flujo, credenciales).

Principios completos: `{{PRINCIPLES}}` (léelos antes de la primera tarea de la sesión si no los conoces).
