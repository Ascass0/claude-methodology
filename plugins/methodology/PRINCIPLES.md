# Principios de desarrollo

Aplican a todo repo que adopte claude-methodology. **DEBE**, **NO DEBE**, **DEBERÍA** y **PUEDE** según RFC 2119.
Cada regla indica cómo se impone entre corchetes: **[script]** (`mth` bloquea), **[hook]**, **[GitHub]** (el remoto) o **[criterio]** (revisores). Lo automatizable se automatiza.

## Índice

0. [Precedencia](#0-precedencia)
1. [Desarrollo dirigido por specs](#1-desarrollo-dirigido-por-specs)
2. [Diseño](#2-diseño)
3. [Errores y excepciones](#3-errores-y-excepciones)
4. [Trazabilidad y observabilidad](#4-trazabilidad-y-observabilidad)
5. [Código](#5-código)
6. [Tests](#6-tests)
7. [Documentación](#7-documentación)
8. [Seguridad](#8-seguridad)
9. [Git](#9-git)
10. [Revisión](#10-revisión)
11. [Autonomía](#11-autonomía)
12. [Proporcionalidad](#12-proporcionalidad)
13. [Definición de hecho](#13-definición-de-hecho)

## 0. Precedencia

Ante un choque gana el primero: 1. **Seguridad** · 2. **Fail-safe / fail-fast** · 3. **Corrección** (cumple la spec) · 4. **Trazabilidad** · 5. **Parsimonia** · 6. **Estilo**.

- Un revisor que pide simplificar lo que existe por seguridad o por un modo de fallo diseñado se equivoca.
- Uno que pide robustez sin un modo de fallo identificado, también.

## 1. Desarrollo dirigido por specs

- Toda feature DEBE partir de una spec aprobada; si no existe, se escribe primero en la rama de la feature. [script: `mth integrate` rechaza una `feat` cuyo fragmento no referencie su spec]
- Tres documentos que NO DEBEN mezclarse:

  | Documento | Responde a | Ubicación | Estados |
  |---|---|---|---|
  | Spec | Qué se construye y cómo se acepta | `specs/features/` | borrador → aprobada → implementada → sustituida |
  | ADR | Por qué se decidió | `specs/adr/<categoría>/` | propuesto → aceptado → sustituido / obsoleto |
  | Docs | Cómo funciona y se usa | `docs/` | se actualizan con el código |

- Toda spec DEBE tener criterios de aceptación verificables con ID (`AC-01`) y tabla de modos de fallo con ID (`FM-01`). [criterio; `mth trace` valida el formato compacto, §7]
- Spec `implementada` ⇒ cada criterio DEBE tener un test con `verifies: SPEC-NNNN/AC-NN`. [script: `mth trace`]
- Una decisión estructural (arquitectura, dependencia nueva, formato de datos, protocolo, cambio de un principio) DEBE tener ADR antes de implementarse. [criterio]
- Specs y ADR NO DEBEN reescribirse para justificar el código: si la spec estaba mal, se corrige con su motivo y después el código. [criterio]
- Los IDs DEBEN ser únicos y toda referencia DEBE apuntar a un ID definido. [script]

## 2. Diseño

- **Design for Failure.** Todo componente DEBE identificar sus modos de fallo (dependencias caídas, timeouts, datos inválidos, recursos agotados, concurrencia, cancelación) y diseñar la respuesta a cada uno; los de una feature van en su spec. [criterio]
- **Fail-fast** ante errores de programación o configuración (configuración inválida, invariantes rotas, precondiciones incumplidas): se detectan al arrancar si es posible, con un mensaje que dice qué falla y cómo arreglarlo. [criterio]
- **Fail-safe** ante fallos en ejecución: el sistema DEBE ir a un estado seguro y conocido. Por defecto **denegar, no degradar**: no se relaja una restricción, un permiso ni un aislamiento para seguir funcionando. [criterio]
- **Límites explícitos.** Toda operación externa DEBE tener timeout; toda entrada, un tamaño máximo; todo reintento, un máximo con espera creciente. Nada espera para siempre ni crece sin límite. [criterio]
- **Idempotencia.** Lo que puede repetirse tras un fallo (reintentos, reanudaciones, tareas programadas) DEBE dar el mismo resultado al repetirse. [criterio]
- **Parsimonia.** Lo más simple que funcione, pero no más. NO DEBEN añadirse abstracciones, configuración ni extensibilidad para necesidades que no existen hoy (YAGNI). La robustez que exige un modo de fallo identificado no es complejidad innecesaria. [criterio]
- **Dependencias explícitas, sin estado global oculto.** Un componente DEBE recibir lo que usa (parámetro o constructor), no tomarlo de un singleton, global mutable o registro estático; la instancia única se decide en la raíz de composición. Las constantes inmutables no son estado global. [criterio]
- **Bajo acoplamiento.** Los módulos se comunican por contratos estrechos y NO DEBEN depender de los detalles internos de otro; cambiar una implementación sin cambiar su contrato NO DEBE obligar a tocar otros. Las dependencias externas (base de datos, red, reloj, ficheros, proveedores) se acceden por una frontera propia. [criterio]
- **Testable por diseño.** La lógica de dominio DEBE estar separada de la E/S: sus tests unitarios no necesitan base de datos, red ni servicios reales (dobles inyectados en las fronteras). Si solo se prueba con infraestructura real, el problema es de diseño. [criterio]
- **Optimización con evidencia.** NO DEBE optimizarse a costa de claridad sin un requisito de rendimiento en la spec o una medición (profiling, benchmark) citada en el commit. Elegir desde el inicio una estructura o algoritmo adecuados no es optimización prematura. [criterio]
- **Estándares primero.** NO DEBE reinventarse lo que ya resuelve un estándar, la biblioteca estándar o una dependencia madura; se adapta y se documenta la desviación. [criterio]
- **Mínimo privilegio.** Cada componente tiene solo los permisos, credenciales y accesos que necesita. [criterio]
- **Determinismo.** Lo que resuelve código determinista NO DEBE delegarse en un modelo de lenguaje. [criterio]

### SOLID

DEBE seguirse en clases, módulos y componentes, con proporcionalidad: la parsimonia sigue prohibiendo la extensibilidad especulativa y una función o script pequeño no necesita interfaces.

- **S · Responsabilidad única.** Cada clase o módulo DEBE tener una sola razón para cambiar: un actor o aspecto (dominio, persistencia, presentación, transporte). Si dos cambios independientes tocan el mismo módulo, se separa. [criterio]
- **O · Abierto/cerrado.** Con al menos dos variantes reales (o si la spec las exige), una variante nueva DEBE entrar añadiendo una implementación sin modificar a quien la usa. Antes, NO DEBE crearse el punto de extensión: se modifica el código. [criterio]
- **L · Sustitución de Liskov.** Toda implementación de un contrato (subclase, interfaz, doble) DEBE poder sustituir a otra sin que quien la usa lo note: sin precondiciones más fuertes, sin garantías más débiles, sin errores ajenos al contrato, sin métodos sin implementar. Con varias implementaciones, DEBERÍA existir un test de contrato que todas pasen. [criterio]
- **I · Segregación de interfaces.** Las interfaces DEBEN ser pequeñas y definirse por lo que necesita quien las usa; nadie depende de métodos que no usa. Concreta el bajo acoplamiento. [criterio]
- **D · Inversión de dependencias.** El dominio DEBE definir las abstracciones que necesita (repositorios, relojes, clientes, notificadores) y la infraestructura las implementa: las dependencias apuntan al dominio, nunca al revés. La implementación concreta se elige en la raíz de composición, como exige la regla de dependencias explícitas. [criterio]

## 3. Errores y excepciones

- **Captura específica** donde se pueda actuar: reintentar, compensar, liberar recursos o pasar a un estado seguro. [criterio]
- **Captura genérica solo en los límites** (entrypoint, handler de petición, bucle de worker, runner de tareas, hook): registrar con contexto, trazar y convertir el fallo en una respuesta controlada. [criterio]
- Un error NO DEBE tragarse en silencio: un `except` que no re-lanza, no registra y no actúa es un bug. [criterio]
- Al envolver un error se DEBE conservar la causa (`raise X from e` o equivalente). [criterio]
- Los errores esperados DEBERÍAN tener tipos propios del dominio y una categoría estable (validación, no encontrado, conflicto, dependencia, tiempo agotado, interno). [criterio]
- Los mensajes DEBEN decir qué falló, con qué entrada (sin secretos) y, si se sabe, cómo arreglarlo. [criterio]
- Los recursos DEBEN liberarse en todos los caminos (context managers, `finally`, `defer`). [criterio]
- Un error de programador (bug) NO DEBE presentarse como error del usuario, ni al revés. [criterio]

## 4. Trazabilidad y observabilidad

Se traza el flujo normal y el de errores.

- **Logs estructurados** (clave-valor o JSON) con nivel, componente, operación y resultado. [criterio]
- **ID de correlación** propagado de extremo a extremo (petición, tarea, ejecución) y presente en cada log y error de esa operación. [criterio]
- **Niveles:** `ERROR` falló y requiere atención · `WARNING` degradación o anomalía recuperada · `INFO` hitos del flujo normal · `DEBUG` detalle de diagnóstico. [criterio]
- **Errores trazables:** todo error registrado incluye categoría, causa encadenada e ID de correlación. [criterio]
- **Secretos nunca** en logs, trazas, mensajes de error, artefactos ni commits: se redactan. [criterio]
- Si el proyecto lo admite, DEBERÍA usarse OpenTelemetry en lugar de un formato propio. [criterio]
- **Trazabilidad del trabajo:** spec → ADR → código → test → commit → PR → versión; cada eslabón referencia al anterior por ID. [script: `mth trace`, trailer `Refs:`, cuerpo del PR, changelog]

## 5. Código

- **Idioma:** identificadores, comentarios, docstrings y commits en inglés, sea cual sea el idioma de la documentación. [criterio]
- **Documentación en el código** según el estándar del lenguaje (PEP 257 estilo Google, JSDoc/TSDoc, Javadoc, Doxygen, rustdoc…):
  - Toda función o método público DEBE decir qué hace (una línea), parámetros, retorno, excepciones y efectos laterales relevantes. [criterio]
  - Con tipos en la firma, NO DEBEN repetirse en la documentación. [criterio]
  - Lo privado y obvio NO DEBE documentarse; el comentario explica el porqué, nunca el qué. [criterio]
- **Referencias a decisiones:** el código que implementa una decisión no obvia DEBE citar `ADR-NNNN` o `SPEC-NNNN` en un comentario breve, solo en ese punto. [script: `mth trace` valida las referencias]
- **Decoradores** (o anotaciones, middleware, wrappers) DEBERÍAN usarse para aspectos transversales: trazas, métricas, reintentos acotados, validación, control de acceso. NO DEBEN contener lógica de negocio, DEBEN preservar firma y metadatos y NO DEBEN tragarse excepciones. [criterio]
- **Configuración fuera del código**, validada al arrancar (fail-fast). [criterio]
- Sin código muerto, sin código comentado y sin `TODO` sin issue o spec. [criterio]
- **Tamaño de fichero:** un fichero versionado NO DEBE superar `limits.max_file_lines` (1000 por defecto) salvo excepción declarada con techo (`max_lines`) y motivo (`reason`). El trinquete actúa sobre la rama: hacer crecer un fichero por encima del límite es error, tocarlo sin hacerlo crecer es aviso; una excepción caducada es error. [script: `mth trace`; criterio: `revisor-diseno` valora el `reason`]
- **Funciones pequeñas y de una responsabilidad:** un nombre que necesita «y» describe dos funciones. [criterio]
- **Nombres que revelan intención.** Los identificadores DEBEN decir qué representan en el dominio. NO DEBEN usarse nombres de una letra (salvo índices y lambdas de una línea), abreviaturas crípticas, sufijos numéricos (`data2`, `result_new`) ni genéricos (`data`, `info`, `tmp`, `manager`, `helper`) fuera de ámbitos de pocas líneas. Los booleanos son predicados (`is_valid`, `has_access`). [criterio]
- **Sin duplicación de conocimiento (DRY).** Una regla de negocio, validación, constante o formato DEBE vivir en un único sitio. Se abstrae desde la tercera repetición, o antes si la duplicación ya causó un bug. Dos fragmentos parecidos que cambian por motivos distintos no son duplicación y NO DEBEN unificarse a la fuerza. [criterio]

Los antipatrones **STUPID** (Singleton, Tight coupling, Untestability, Premature optimization, Indescriptive naming, Duplication) violan seis reglas: dependencias explícitas, bajo acoplamiento, testable por diseño, optimización con evidencia (§2), nombres que revelan intención y sin duplicación (§5). Su reverso es [SOLID](#solid). Un revisor que los detecte DEBE citar la regla incumplida.

## 6. Tests

Los necesarios y ninguno más:

- Un test por **criterio de aceptación** (con la triangulación de abajo). [script]
- Un test por **modo de fallo** diseñado en la spec. [criterio]
- Un test de **regresión** por bug corregido, que falle sin el fix. [criterio]
- Tests de las **funciones públicas con lógica no trivial** no cubiertas por lo anterior. [criterio]

Cada test declara por qué existe (ADR-0015):

- **Etiqueta obligatoria** en el comentario del test: `verifies: SPEC-NNNN/AC-NN`, `verifies: SPEC-NNNN/FM-NN`, `regression: <referencia>` o `unit: <símbolo público>`. Un test sin etiqueta es andamiaje: error en `mth trace` y bloquea `mth integrate` (aviso en ficheros legados). [script: `mth trace`]
- **Triangulación:** todo AC cuya salida dependa de la entrada DEBE tener al menos dos ejemplos de clases de equivalencia distintas (dos tests o uno parametrizado). Un AC sin entrada variable queda exento. [criterio; `mth trace` avisa de los AC con un único test]
- **Andamiaje fuera:** dos tests de la misma clase para el mismo AC, uno sobra; un test se conserva solo si aporta una clase, un límite o un modo de fallo propio. [criterio]
- Una implementación con casos especiales para los valores del test NO DEBE aceptarse. [criterio]

Además:

- Los tests DEBEN ser deterministas: sin reloj, orden ni red, salvo los de integración, marcados como tales. [criterio]
- NO DEBEN escribirse tests de getters triviales, de la biblioteca estándar ni de detalles de implementación que bloqueen refactorizaciones. [criterio]
- Cada commit DEBE dejar los tests en verde (`git bisect`). [criterio; los gates de `mth integrate` ejecutan los tests]

## 7. Documentación

- La documentación DEBE actualizarse en la misma rama que el cambio; una feature sin docs no está hecha. [criterio]
- Una única fuente de verdad: se enlaza, no se duplica. [criterio]
- Los enlaces internos DEBEN ser relativos, válidos y apuntar dentro del repo; lo de otro repo, con URL absoluta. [script: `mth trace`]
- Docs, specs, ADR, changelog y PR en el idioma de `language.docs` (español por defecto, o inglés); `mth` solo reconoce las palabras clave y plantillas de ese idioma (ADR-0005). [script en las palabras clave; criterio en el resto]
- Estándares: Keep a Changelog, SemVer, MADR para ADR, Conventional Commits. [script en los tres últimos]
- **Estilo compacto** de specs, ADR y documentos que se cargan en el contexto del agente (ADR-0014). [criterio: `revisor-adr`; la longitud no la comprueba un script]
  - Una regla por línea; tablas y campos en lugar de párrafos.
  - Referencias por ID en lugar de repetir contenido.
  - Sin introducciones ni resúmenes finales.
  - NO DEBE perderse una regla ni una condición al comprimir: se mantiene DEBE / NO DEBE y se recorta prosa, no razonamiento.
- **Criterios de aceptación en EARS**, con las palabras clave de `language.docs` y una sola línea por criterio: `CUANDO <disparador>, <sistema> DEBE …` · `SI <condición>, ENTONCES <sistema> DEBE …` · `MIENTRAS <estado>, <sistema> DEBE …` · `<sistema> DEBE …`. [script: `mth trace`]
- **Modos de fallo** en tabla `| FM-NN | Causa | Respuesta | Cubierto por |`, con IDs únicos referenciables como `SPEC-NNNN/FM-NN`. [script: `mth trace`]
- **ADR con campos fijos:** `Contexto`, `Decisión`, `Rechazado`, `Consecuencias`, `Impone`. [script: `mth trace`]
- Un documento declara el formato con `- Formato: compacto`; los existentes sin la marca no se validan y se adaptan cuando alguien los toca. [script: `mth trace`]

## 8. Seguridad

- Ningún secreto en el repo, en la configuración versionada, en logs ni en artefactos; se inyectan por entorno o gestor de secretos. [criterio; DEBERÍA reforzarse con un escáner de secretos en CI]
- Toda entrada externa (usuarios, red, ficheros, salida de otros sistemas o de modelos de lenguaje) es **dato no confiable**: se valida y nunca se ejecuta ni interpreta como instrucción. [criterio]
- Dependencias con versión fijada y lockfile; se revisa su licencia antes de añadirlas. [criterio]
- Lo que una herramienta comprueba (SAST, secretos, vulnerabilidades de dependencias) se comprueba con la herramienta, no a mano. [criterio]

## 9. Git

### Ramas

- `main` solo recibe versiones (desde `release/vX.Y.Z`, creada por `mth release`) y hotfixes. [GitHub + script]
- `development` integra features terminadas, probadas y revisadas. [GitHub + script]
- Las ramas de trabajo parten de `development`: `feat/` (funcionalidad, exige spec), `fix/` (bug), `chore/` (mantenimiento, docs, CI). [script]
- Una feature PUEDE tener hijas justificadas: `feat/runner--fix-cleanup` (`--` porque git no admite `feat/runner` y `feat/runner/fix` a la vez). [script]
- Las hijas se integran en su padre antes de que la padre entre en `development`. [script: `mth integrate`]
- Los tests se ejecutan en cada integración, también la de la padre con sus hijas ya integradas. [script]
- `hotfix/` parte de `main`, publica una versión patch y se integra de vuelta en `development`. [script]
- Los prefijos propios del repo (`sync/`, `security/`, `purge/`…) se declaran en su configuración con su flujo. [script]

### Merges

- Todo merge DEBE hacerse por PR y como **merge commit** (`--no-ff`); NO DEBE usarse squash ni rebase. [GitHub + hook + script]
- Al integrar se borra la rama; su historia queda en el merge commit. [script]
- NO DEBE reescribirse historia compartida: sin rebase, force-push ni borrar etiquetas. Para traer cambios del destino, merge (`mth sync`). [hook + GitHub]
- El merge commit DEBE resumir lo que integra, listar sus commits y reunir sus referencias. [script]

### Commits

- **Temáticos:** agrupan por relación, no por fichero ni momento; el atómico es la excepción y se justifica en el cuerpo. Un commit temático NO ES un volcado de fin de jornada: tiene un tema identificable y deja la build en verde. [criterio]
- **Conventional Commits** con cuerpo y trailer de referencias [script + hook]:

  ```
  tipo(ámbito): resumen en imperativo, en inglés, ≤ 72 caracteres

  Qué cambia y por qué, en prosa breve.

  Refs: SPEC-NNNN, ADR-NNNN
  ```

- `feat`, `fix`, `refactor` y `perf` DEBEN referenciar una spec, un ADR o un issue; el resto PUEDE usar `Refs: n/a`. [script]
- Un cambio incompatible se marca con `!` y el trailer `BREAKING CHANGE:`. [script]

### Versiones y changelog

- SemVer (`vX.Y.Z`) con etiquetas anotadas sobre el merge commit de `main`. [script]
- Cada rama de primer nivel aporta un **fragmento** `changes/<tipo>-<slug>.md` con su `bump` y sus referencias; las ramas paralelas nunca entran en conflicto. [script]
- Al publicar, los fragmentos pasan al `CHANGELOG.md` (Keep a Changelog) y se borran; la versión sale del mayor `bump`. [script]
- La descripción del PR contiene resumen, referencias, fragmento y resultado de la revisión. [script]

## 10. Revisión

- Los revisores son los agentes que declara cada repo, con **contexto limpio**: diff, specs y ADR afectados y estos principios; nunca la conversación del autor. Se declaran con el catálogo (`mth agents add`). [criterio]
- Antes, lo determinista (tests, lint, `mth trace`, escáneres): un agente no revisa lo que una herramienta comprueba. [criterio]
- Severidad de cada hallazgo: **bloqueante** (incumple un DEBE o un criterio de aceptación, o introduce un riesgo), **importante** (incumple un DEBERÍA) o **sugerencia**. Solo los bloqueantes impiden integrar. [script]
- Los conflictos entre revisores se resuelven con la precedencia (§0). [criterio]
- Toda revisión se registra sobre el commit exacto; un commit posterior la invalida. [script]

## 11. Autonomía

- Se trabaja de forma autónoma: crear ramas, commits, integrar, publicar y lanzar skills NO requiere permiso. Es `autonomy.level = full`, el valor por defecto.
- Un repo con supervisión elige `until-pr` (integrar y publicar piden confirmación) o `supervised` (además, cada rama nueva, commit y push). Una confirmación rechazada NO DEBE sortearse por otra vía. [hook: el guard pide la confirmación (ADR-0004)]
- La autonomía se apoya en gates deterministas: no se integra con tests en rojo, trazabilidad rota, revisiones pendientes ni CI en rojo. [script]
- Se DEBE detener el trabajo y avisar solo si:
  1. dos specs o principios se contradicen y la precedencia no lo resuelve;
  2. un gate falla tres veces seguidas por la misma causa;
  3. la tarea exige algo fuera de las specs con impacto irreversible (borrar datos, publicar fuera del flujo, tocar credenciales o infraestructura compartida).
- Ante una ambigüedad menor: la interpretación más conservadora, documentada en la spec o el PR, y se continúa.

## 12. Proporcionalidad

El proceso escala con el impacto; lo determina el tipo de cambio, no la intuición:

| Nivel | Cuándo | Exige |
|---|---|---|
| Mantenimiento | Typos, docs, CI, dependencias sin cambio de comportamiento | Rama `chore/`, commits con formato. Sin spec, fragmento ni revisión |
| Corrección | Bug con comportamiento esperado ya definido | Rama `fix/`, test de regresión, fragmento, revisión |
| Feature | Comportamiento nuevo | Spec aprobada, rama `feat/`, tests por AC y modo de fallo, docs, fragmento, revisión |
| Estructural | Arquitectura, dependencias, formatos, principios | Lo anterior + ADR aceptado antes de implementar |

## 13. Definición de hecho

- [ ] Cumple todos los criterios de aceptación de su spec y la spec está `implementada` (features).
- [ ] Cada criterio y cada modo de fallo tiene su test; todos en verde.
- [ ] Documentación, specs y ADR afectados actualizados.
- [ ] `mth trace` sin hallazgos.
- [ ] Fragmento de changelog completo (si aplica).
- [ ] Todos los revisores han aprobado el HEAD final sin bloqueantes (si aplica).
- [ ] Ramas hijas integradas.
- [ ] CI en verde.
