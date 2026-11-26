# ADR-0009 · El número de bloqueantes lo calcula mth

- Estado: aceptado
- Fecha: 2026-11-23
- Categoría: process
- Formato: compacto

## Contexto

- El gate de integración exige un registro de cada revisor con 0 bloqueantes sobre el HEAD.
- Hasta ahora lo declaraba el propio revisor en `BLOQUEANTES: <n>` (SPEC-0001/AC-12): un modelo puede contar mal o declarar 0 con un bloqueante en el cuerpo.
- Ante un informe con formato roto se relanzaban agentes hasta que saliera bien: el gate dependía de la suerte.
- Lo guardado a veces era un resumen posterior, no auditable (PRINCIPLES §10).

## Decisión

1. El número de bloqueantes DEBE salir de un cálculo de `mth` sobre los hallazgos del informe; la línea del agente solo se contrasta.
2. Una discrepancia o un formato ilegible DEBEN registrarse como revisión **fallida** (estado seguro), con contador de intentos.
3. `mth` DEBE archivar el informe literal con el SHA y su huella.
4. Ante un fallo DEBE pedirse **una** corrección al mismo agente, con su contexto; NO DEBE lanzarse otro desde cero.

Detalle en [SPEC-0013](../../features/SPEC-0013-registro-de-revisiones-calculado-por-mth.md).

## Rechazado

- Fiarse de la última línea: el modelo decide el gate.
- Calcular y dar la razón a `mth` cuando el agente discrepa: esconde un informe incoherente, señal de un revisor que no hizo bien su trabajo.
- Relanzar sin límite hasta que el formato salga: convierte el gate en lotería; una corrección y un contador visible.
- Comprobar la corrección de los hallazgos con otro agente: fuera de alcance; repite coste y problema de confianza.

## Consecuencias

- **+** El número que decide la integración no depende de lo que afirme el modelo.
- **−** Un formato estricto produce más rechazos al principio; los reintentos y sus motivos quedan visibles y apuntan a prompts de revisor que corregir.
- **riesgo** `mth` no valida que la severidad esté bien asignada: sigue siendo juicio del revisor.

## Impone

- [script] `mthlib/review.py`: cálculo, registro y archivo literal del informe (`mth review`).
- [criterio] `mth integrate`: exige el registro sin bloqueantes sobre el HEAD.
