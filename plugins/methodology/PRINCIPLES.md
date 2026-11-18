# Principios de desarrollo

Este documento define cómo se desarrolla en cualquier repositorio que adopte claude-methodology. Las palabras **DEBE**, **NO DEBE**, **DEBERÍA** y **PUEDE** tienen el sentido de la RFC 2119: obligación, prohibición, recomendación fuerte y opción.

Cada regla indica entre corchetes cómo se impone: **[script]** (lo comprueba `mth` y bloquea), **[hook]** (lo bloquea un hook), **[GitHub]** (lo impone el repositorio remoto) o **[criterio]** (depende del juicio de quien desarrolla y de los revisores). Lo que puede automatizarse se automatiza; el resto es criterio.

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

Cuando dos principios chocan, gana el primero de esta lista:

1. **Seguridad**
2. **Fail-safe / fail-fast**
3. **Corrección** (cumple la spec)
4. **Trazabilidad**
5. **Parsimonia**
6. **Estilo**

Un revisor que pide simplificar algo que existe por seguridad o por un modo de fallo diseñado está equivocado; uno que pide añadir robustez sin un modo de fallo identificado, también.

## 1. Desarrollo dirigido por specs

- Toda feature DEBE partir de una spec aprobada. Si no existe, se escribe primero, dentro de la rama de la feature. [script: `mth integrate` rechaza una `feat` cuyo fragmento no referencie su spec]
- Se distinguen tres tipos de documento y NO DEBEN mezclarse:

  | Documento | Responde a | Ubicación por defecto | Estados |
  |---|---|---|---|
  | Spec | Qué se construye y cómo se acepta | `specs/features/` | borrador → aprobada → implementada → sustituida |
  | ADR | Por qué se decidió así | `specs/adr/<categoría>/` | propuesto → aceptado → sustituido / obsoleto |
  | Docs | Cómo funciona y cómo se usa | `docs/` | se actualizan con el código |

- Toda spec DEBE tener criterios de aceptación verificables con ID (`AC-01`) y una tabla de modos de fallo. [criterio]
- Una spec en estado `implementada` DEBE tener cada criterio cubierto por al menos un test que lo declare con `verifies: SPEC-NNNN/AC-NN`. [script: `mth trace`]
- Una decisión estructural (arquitectura, dependencia nueva, formato de datos, protocolo, cambio de un principio) DEBE registrarse en un ADR antes de implementarla. [criterio]
- Las specs y ADR NO DEBEN reescribirse para justificar el código: si la implementación revela que la spec estaba mal, se corrige la spec (con su motivo) y después el código. [criterio]
- Los IDs DEBEN ser únicos y toda referencia DEBE apuntar a un ID definido. [script]

## 2. Diseño

- **Design for Failure.** Todo componente DEBE identificar sus modos de fallo (dependencias caídas, timeouts, datos inválidos, recursos agotados, concurrencia, cancelación) y diseñar la respuesta a cada uno. Los modos de fallo de una feature van en su spec. [criterio]
- **Fail-fast** para lo que es un error de programación o de configuración: configuración inválida, invariantes rotas, precondiciones incumplidas. Se detecta lo antes posible (idealmente al arrancar) y se detiene con un mensaje que dice qué falla y cómo arreglarlo. [criterio]
- **Fail-safe** para los fallos en ejecución: ante un fallo, el sistema DEBE ir a un estado seguro y conocido. El estado seguro por defecto es **denegar, no degradar**: no se relaja una restricción, un permiso o un nivel de aislamiento para seguir funcionando. [criterio]
- **Límites explícitos.** Toda operación externa DEBE tener timeout; toda entrada, un tamaño máximo; todo reintento, un número máximo con espera creciente. Nada espera para siempre ni crece sin límite. [criterio]
- **Idempotencia.** Las operaciones que pueden repetirse tras un fallo (reintentos, reanudaciones, tareas programadas) DEBEN poder ejecutarse varias veces con el mismo resultado. [criterio]
- **Parsimonia.** Lo más simple que funcione, pero no más simple. NO DEBEN añadirse abstracciones, configuración ni extensibilidad para necesidades que no existen hoy (YAGNI). La robustez exigida por un modo de fallo identificado no es complejidad innecesaria. [criterio]
- **Dependencias explícitas, sin estado global oculto.** Un componente DEBE recibir lo que usa (por parámetro o constructor) en lugar de obtenerlo de un singleton, una variable global mutable o un registro estático. Que algo tenga una sola instancia se decide en la raíz de composición (el entrypoint), no dentro de la clase. Las constantes inmutables no son estado global. [criterio]
- **Bajo acoplamiento.** Los módulos se comunican por contratos estrechos (funciones, interfaces, tipos de datos) y NO DEBEN depender de los detalles internos de otro. Cambiar la implementación de un componente sin cambiar su contrato NO DEBE obligar a tocar otros. Las dependencias externas (base de datos, red, reloj, sistema de ficheros, proveedores) se acceden a través de una frontera propia, no repartidas por la lógica. [criterio]
- **Testable por diseño.** La lógica de dominio DEBE estar separada de la E/S, de modo que sus tests unitarios no necesiten base de datos, red ni servicios reales: los dobles de prueba se inyectan en las fronteras anteriores. Un código que solo puede probarse con la infraestructura real tiene un problema de diseño, no de tests. [criterio]
- **Optimización con evidencia.** NO DEBE optimizarse el rendimiento a costa de claridad sin un requisito de rendimiento en la spec o una medición (profiling, benchmark) que demuestre el problema; la medición se cita en el commit. Elegir desde el principio una estructura de datos o un algoritmo de complejidad adecuada no es optimización prematura. [criterio]
- **Estándares primero.** NO DEBE reinventarse lo que ya resuelve un estándar, la biblioteca estándar o una dependencia madura y mantenida. Se adapta al caso de uso; se documenta la desviación cuando existe. [criterio]
- **Mínimo privilegio.** Cada componente tiene solo los permisos, credenciales y accesos que necesita. [criterio]
- **Determinismo.** Lo que puede resolverse con código determinista NO DEBE delegarse en un modelo de lenguaje. [criterio]

### SOLID

SOLID es la práctica de diseño que DEBE seguirse en clases, módulos y componentes. Se aplica con proporcionalidad: la parsimonia sigue prohibiendo la extensibilidad especulativa, y una función o un script pequeño no necesitan interfaces.

- **S · Responsabilidad única.** Cada clase o módulo DEBE tener una sola razón para cambiar: responde ante un único actor o aspecto (dominio, persistencia, presentación, transporte). Si dos cambios independientes obligan a tocar el mismo módulo, se separa. [criterio]
- **O · Abierto/cerrado.** Cuando existen al menos dos variantes reales de un comportamiento, o la spec las exige, el código DEBE admitir una variante nueva añadiendo una implementación, sin modificar a quienes lo usan. Antes de eso NO DEBE crearse el punto de extensión: se modifica el código directamente. [criterio]
- **L · Sustitución de Liskov.** Toda implementación de un contrato (subclase, implementación de una interfaz, doble de prueba) DEBE poder sustituir a cualquier otra sin que quien lo usa lo note: no exige precondiciones más fuertes, no ofrece garantías más débiles, no lanza errores ajenos al contrato y no deja métodos sin implementar. Cuando un contrato tiene varias implementaciones, DEBERÍA existir un test de contrato que pasen todas. [criterio]
- **I · Segregación de interfaces.** Las interfaces DEBEN ser pequeñas y definirse según lo que necesita quien las usa: ningún consumidor depende de métodos que no usa. Concreta la regla de bajo acoplamiento. [criterio]
- **D · Inversión de dependencias.** La lógica de dominio DEBE definir las abstracciones que necesita (repositorios, relojes, clientes, notificadores) y la infraestructura las implementa: las dependencias del código apuntan hacia el dominio, nunca del dominio a la infraestructura. La implementación concreta se elige en la raíz de composición, como exige la regla de dependencias explícitas. [criterio]

## 3. Errores y excepciones

- **Captura específica** donde se pueda actuar: reintentar, compensar, liberar recursos o pasar a un estado seguro. [criterio]
- **Captura genérica solo en los límites** del sistema (entrypoint, handler de una petición, bucle de un worker, runner de tareas, hook): para registrar con contexto, trazar y convertir el fallo en una respuesta controlada. En ningún otro sitio. [criterio]
- Un error NO DEBE tragarse en silencio. Un `except` que no re-lanza, no registra y no actúa es un bug. [criterio]
- Al envolver un error se DEBE conservar la causa (`raise X from e` o el equivalente del lenguaje). [criterio]
- Los errores esperados DEBERÍAN modelarse con tipos propios del dominio y una categoría estable (validación, no encontrado, conflicto, dependencia, tiempo agotado, interno). [criterio]
- Los mensajes de error DEBEN decir qué falló, con qué entrada (sin secretos) y, si se sabe, cómo arreglarlo. [criterio]
- Los recursos DEBEN liberarse en todos los caminos (context managers, `finally`, `defer` o equivalente). [criterio]
- Los errores de un programador (bug) NO DEBEN presentarse como errores del usuario, ni al revés. [criterio]

## 4. Trazabilidad y observabilidad

Se traza el flujo normal y el de errores.

- **Logs estructurados** (pares clave-valor o JSON) con nivel, componente, operación y resultado. [criterio]
- **Identificador de correlación** propagado de extremo a extremo (petición, tarea, ejecución) y presente en cada log y en cada error de esa operación. [criterio]
- **Niveles con significado:** `ERROR`, algo falló y requiere atención; `WARNING`, degradación o situación anómala recuperada; `INFO`, hitos del flujo normal; `DEBUG`, detalle para diagnóstico. [criterio]
- **Errores trazables:** todo error registrado incluye su categoría, la causa encadenada y el identificador de correlación. [criterio]
- **Secretos nunca** en logs, trazas, mensajes de error, artefactos ni commits. La trazabilidad no justifica exponer datos sensibles: se redactan. [criterio]
- Si el proyecto lo admite, DEBERÍA usarse OpenTelemetry en lugar de un formato propio. [criterio]
- **Trazabilidad del trabajo:** spec → ADR → código → test → commit → PR → versión. Cada eslabón referencia al anterior por ID. [script: `mth trace`, trailer `Refs:`, cuerpo del PR, changelog]

## 5. Código

- **Idioma:** identificadores, comentarios, docstrings y mensajes de commit en inglés. [criterio]
- **Documentación en el código**, siguiendo el estándar del lenguaje (PEP 257 con estilo Google en Python, JSDoc/TSDoc, Javadoc, Doxygen, rustdoc…):
  - Cada función o método público DEBE tener una definición mínima: qué hace (una línea), parámetros, valor de retorno, excepciones que lanza y efectos laterales relevantes. [criterio]
  - Si el lenguaje tiene tipos, los tipos van en la firma y NO DEBEN repetirse en la documentación. [criterio]
  - Lo privado y obvio NO DEBE documentarse: el comentario explica el porqué, nunca repite el qué. [criterio]
- **Referencias a decisiones:** el código que implementa una decisión no obvia DEBE referenciarla con el formato `ADR-NNNN` (o `SPEC-NNNN`) en un comentario breve. Solo en ese punto, no en todas partes. Las referencias se validan. [script: `mth trace`]
- **Decoradores** (o el mecanismo equivalente: anotaciones, middleware, wrappers) DEBERÍAN usarse para aspectos transversales: trazas, métricas, reintentos acotados, validación, control de acceso. NO DEBEN contener lógica de negocio, DEBEN preservar la firma y los metadatos de la función envuelta y NO DEBEN tragarse excepciones. [criterio]
- **Configuración fuera del código** y validada al arrancar (fail-fast). [criterio]
- **Sin código muerto**, sin código comentado y sin `TODO` sin referencia a un issue o una spec. [criterio]
- **Funciones pequeñas y con una responsabilidad.** Un nombre que necesita "y" describe dos funciones. [criterio]
- **Nombres que revelan intención.** Los identificadores DEBEN decir qué representan en el dominio y para qué sirven. NO DEBEN usarse nombres de una letra (salvo índices y lambdas de una línea), abreviaturas crípticas, sufijos numéricos (`data2`, `result_new`) ni genéricos (`data`, `info`, `tmp`, `manager`, `helper`) fuera de ámbitos de pocas líneas. Los booleanos se nombran como predicados (`is_valid`, `has_access`). [criterio]
- **Sin duplicación de conocimiento (DRY).** Una regla de negocio, una validación, una constante o un formato DEBEN vivir en un único sitio. Se abstrae a partir de la tercera repetición, o antes si la duplicación ya ha causado un bug. Dos fragmentos parecidos que cambian por motivos distintos no son duplicación y NO DEBEN unificarse a la fuerza: el acoplamiento que crea una abstracción equivocada es peor que la copia. [criterio]

Los antipatrones **STUPID** (Singleton, Tight coupling, Untestability, Premature optimization, Indescriptive naming, Duplication) son la violación de seis reglas: dependencias explícitas, bajo acoplamiento, testable por diseño y optimización con evidencia (apartado 2), y nombres que revelan intención y sin duplicación de conocimiento (este apartado). Son el reverso de la buena práctica, que es [SOLID](#solid). Un revisor que los detecte DEBE citar la regla incumplida.

## 6. Tests

Se escriben los tests necesarios y ninguno más. "Necesario" tiene un criterio objetivo:

- Al menos un test por **criterio de aceptación**. [script]
- Al menos un test por **modo de fallo** diseñado en la spec. [criterio]
- Un test de **regresión** por cada bug corregido, que falle sin el fix. [criterio]
- Tests de las **funciones públicas con lógica no trivial** que no queden cubiertas por lo anterior. [criterio]

Además:

- Los tests DEBEN ser deterministas: sin dependencia del reloj, del orden ni de la red, salvo los de integración, que se marcan como tales. [criterio]
- NO DEBEN escribirse tests de getters triviales, de la biblioteca estándar ni de detalles de implementación que bloqueen refactorizaciones. [criterio]
- Cada commit DEBE dejar los tests en verde, para conservar `git bisect`. [criterio; los gates de `mth integrate` ejecutan los tests]

## 7. Documentación

- La documentación DEBE actualizarse en la misma rama que el cambio que la motiva. Una feature sin sus docs no está hecha. [criterio]
- Una única fuente de verdad: se enlaza, no se duplica. [criterio]
- Los enlaces internos DEBEN ser relativos, válidos y apuntar dentro del repositorio. Lo que vive en otro repositorio se enlaza con URL absoluta. [script: `mth trace`]
- Docs, specs, ADR, changelog y descripciones de PR en español. [criterio]
- Se sigue el estándar aplicable: Keep a Changelog, SemVer, MADR para ADR, Conventional Commits. [script en los tres últimos]

## 8. Seguridad

- Ningún secreto en el repositorio, en la configuración versionada, en logs ni en artefactos. Los secretos se inyectan por entorno o por un gestor de secretos. [criterio; DEBERÍA reforzarse con un escáner de secretos en CI]
- Toda entrada externa (usuarios, red, ficheros, salida de otros sistemas o de modelos de lenguaje) es **dato no confiable**: se valida y nunca se ejecuta ni se interpreta como instrucción. [criterio]
- Dependencias con versión fijada y lockfile; se revisa su licencia antes de añadirlas. [criterio]
- Lo que una herramienta puede comprobar (SAST, secretos, vulnerabilidades de dependencias) se comprueba con la herramienta, no con revisión manual. [criterio]

## 9. Git

### Ramas

```
main ─────────●──────────────●────────── (solo versiones: merge commit + tag)
              │              │
hotfix/<slug> │   ┌──●──┐    │  (desde main → main + tag patch → development)
              │   │     │    │
development ──●───┴─────●────●────────── (integra features 100 % funcionales)
              │              │
feat|fix|chore/<slug> ──●──●──●  (desde development)
                         \
                  <rama>--<tipo>-<slug>  (hijas: fix, feat, refactor, test, docs, chore)
```

- `main` solo recibe versiones (desde `release/vX.Y.Z`, creada por `mth release`) y hotfixes. [GitHub + script]
- `development` integra features terminadas, probadas y revisadas. [GitHub + script]
- Las ramas de trabajo parten de `development`: `feat/` (funcionalidad, exige spec), `fix/` (bug) y `chore/` (mantenimiento, docs, CI). [script]
- Una feature PUEDE tener ramas hijas justificadas: `feat/runner--fix-cleanup`. Se usa `--` porque git no admite `feat/runner` y `feat/runner/fix` a la vez. [script]
- Las hijas se integran siempre en su rama padre antes de que la padre se integre en `development`. [script: `mth integrate` lo comprueba]
- Los tests se ejecutan en cada integración, incluida la de la padre con todas sus hijas ya integradas. [script]
- `hotfix/` parte de `main`, publica una versión patch y se integra de vuelta en `development`. [script]
- Los prefijos propios de un repo (por ejemplo, `sync/`, `security/`, `purge/`) se declaran en su configuración con su flujo. [script]

### Merges

- Todo merge DEBE hacerse por PR y como **merge commit** (`--no-ff`). NO DEBE usarse squash ni rebase. [GitHub + hook + script]
- Al integrar se borra la rama, pero su historia se conserva en el merge commit. [script]
- NO DEBE reescribirse historia compartida: sin rebase, sin force-push, sin borrar etiquetas. Para traer cambios de la rama destino se usa merge (`mth sync`). [hook + GitHub]
- El mensaje del merge commit DEBE resumir lo que integra, listar sus commits y reunir sus referencias. [script]

### Commits

- Los commits son **temáticos**: agrupan los cambios por relación, no por fichero ni por momento. Un commit atómico es la excepción y se justifica en su cuerpo. [criterio]
- Un commit temático NO ES un volcado de fin de jornada: cada commit tiene un tema identificable y deja la build en verde. [criterio]
- Formato **Conventional Commits** con cuerpo y trailer de referencias [script + hook]:

  ```
  tipo(ámbito): resumen en imperativo, en inglés, ≤ 72 caracteres

  Qué cambia y por qué, en prosa breve.

  Refs: SPEC-NNNN, ADR-NNNN
  ```

- `feat`, `fix`, `refactor` y `perf` DEBEN referenciar una spec, un ADR o un issue. El resto PUEDE usar `Refs: n/a`. [script]
- Un cambio incompatible se marca con `!` y el trailer `BREAKING CHANGE:`. [script]

### Versiones y changelog

- Versionado semántico (`vX.Y.Z`) con etiquetas anotadas sobre el merge commit de `main`. [script]
- Cada rama de trabajo de primer nivel aporta un **fragmento** de changelog (`changes/<tipo>-<slug>.md`) con su incremento de versión (`bump`) y sus referencias. Varias ramas en paralelo nunca entran en conflicto. [script]
- Al publicar, los fragmentos se incorporan al `CHANGELOG.md` global (Keep a Changelog) y se borran; la versión se calcula del mayor `bump`. [script]
- La descripción del PR de la feature contiene su resumen, sus referencias, su fragmento y el resultado de la revisión. [script]

## 10. Revisión

- Los revisores son los agentes que declara cada repositorio. Revisan con **contexto limpio**: diff, specs y ADR afectados y estos principios; nunca la conversación del autor. [criterio]
- Antes de la revisión con agentes se ejecuta lo determinista (tests, lint, `mth trace`, escáneres). Un agente no revisa lo que una herramienta puede comprobar. [criterio]
- Cada hallazgo tiene severidad: **bloqueante** (incumple una regla DEBE, un criterio de aceptación o introduce un riesgo), **importante** (incumple un DEBERÍA) o **sugerencia**. Solo los bloqueantes impiden integrar. [script]
- Los conflictos entre revisores se resuelven con la precedencia del apartado 0. [criterio]
- Toda revisión se registra sobre el commit exacto revisado; un commit posterior la invalida. [script]

## 11. Autonomía

- Se trabaja de forma autónoma: crear ramas, hacer commits, integrar, publicar versiones y lanzar skills NO requiere permiso. La supervisión, si un repositorio la necesita, se añade con un hook en ese repositorio.
- La autonomía se apoya en gates deterministas, no en la confianza: no se integra con tests en rojo, trazabilidad rota, revisiones pendientes o CI en rojo. [script]
- Se DEBE detener el trabajo y avisar solo cuando:
  1. dos specs o principios se contradicen y la precedencia no lo resuelve;
  2. un gate falla tres veces seguidas por la misma causa;
  3. la tarea exige algo fuera de las specs con impacto irreversible (borrar datos, publicar fuera del flujo, tocar credenciales o infraestructura compartida).
- Ante una ambigüedad menor, se elige la interpretación más conservadora, se documenta en la spec o en el PR y se continúa.

## 12. Proporcionalidad

El proceso escala con el impacto. El nivel lo determina el tipo de cambio, no la intuición:

| Nivel | Cuándo | Qué exige |
|---|---|---|
| Mantenimiento | Typos, docs, CI, dependencias sin cambio de comportamiento | Rama `chore/`, commits con formato. Sin spec, fragmento ni revisión |
| Corrección | Bug con comportamiento esperado ya definido | Rama `fix/`, test de regresión, fragmento, revisión |
| Feature | Comportamiento nuevo | Spec aprobada, rama `feat/`, tests por AC y modo de fallo, docs, fragmento, revisión |
| Estructural | Arquitectura, dependencias, formatos, principios | Lo anterior y un ADR aceptado antes de implementar |

## 13. Definición de hecho

Una rama de trabajo está hecha cuando:

- [ ] Cumple todos los criterios de aceptación de su spec y la spec está en `implementada` (features).
- [ ] Cada criterio de aceptación y cada modo de fallo tiene su test; todos en verde.
- [ ] La documentación, las specs y los ADR afectados están actualizados.
- [ ] `mth trace` no reporta hallazgos.
- [ ] El fragmento de changelog está completo (si aplica).
- [ ] Todos los revisores han aprobado el HEAD final sin bloqueantes (si aplica).
- [ ] Sus ramas hijas están integradas.
- [ ] La CI está en verde.
