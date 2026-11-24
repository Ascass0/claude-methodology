# claude-methodology · reglas base

{{AUTONOMY}}

**Precedencia:** seguridad > fail-safe/fail-fast > corrección > trazabilidad > parsimonia > estilo.

**Ciclo:** rama (`mth-branch`) → spec y ADR (`mth-spec`) → código + tests + docs → commits temáticos (`mth-commit`) → revisión (`mth-review`) → integración (`mth-integrate`) → versión (`mth-release`). Detalle: skill `mth-develop`.

**Reglas que no se negocian:**
- Integrar, etiquetar o borrar ramas solo con `mth` (`{{MTH}}`), nunca a mano. Nunca se reescribe historia compartida (sin rebase, squash ni force-push).
- Sin spec no hay feature: se escribe primero. Decisión estructural sin ADR = error.
- Cada criterio de aceptación y cada modo de fallo, al menos un test (`verifies: SPEC-NNNN/AC-NN`).
- Specs y ADR nuevos en formato compacto (`- Formato: compacto`): AC en EARS, modos de fallo `FM-NN`, ADR con campos fijos.
- Excepciones: captura específica donde puedas actuar; genérica solo en los límites; nunca se traga un error; se encadena la causa.
- SOLID (responsabilidad única; extensión sin modificar solo con variantes reales; implementaciones sustituibles; interfaces pequeñas; el dominio define las abstracciones y la infraestructura las implementa). Sin STUPID: dependencias explícitas (no estado global), contratos estrechos, lógica separada de la E/S, sin optimizar sin medir, nombres que revelan intención, cada conocimiento en un solo sitio.
- Código y commits en inglés; docs, specs, changelog y PR en {{DOCS_LANGUAGE}} (`language.docs`).
- Los revisores trabajan con contexto limpio (diff + specs + principios).
- Artefactos de trabajo en `.work/` (local, excluido de git): `plans/`, `merge-request/` (títulos y cuerpos de PR), `security-report/`, `reviews/`, `notes/` (entre sesiones), `tmp/`{{WORK_EXTRA}}. Nunca al repo ni al scratchpad.

**Te detienes y avisas solo si:** dos specs o principios se contradicen y la precedencia no lo resuelve; un gate falla tres veces seguidas por la misma causa; o la tarea exige algo fuera de las specs con impacto irreversible (borrar datos, publicar fuera del flujo, credenciales).

Principios completos: `{{PRINCIPLES}}` (léelos antes de la primera tarea si no los conoces).
