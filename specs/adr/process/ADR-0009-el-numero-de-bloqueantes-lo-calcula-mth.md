# ADR-0009 · El número de bloqueantes lo calcula mth

- Estado: aceptado
- Fecha: 2026-11-23
- Categoría: process

<!-- Estados: propuesto → aceptado → sustituido por ADR-NNNN | obsoleto. Formato basado en MADR. -->

## Contexto

El gate de integración exige un registro de cada revisor con 0 bloqueantes sobre el HEAD. Hasta ahora ese número lo declaraba el propio revisor en `BLOQUEANTES: <n>` (SPEC-0001/AC-12). Un modelo puede contar mal, o declarar 0 con un hallazgo bloqueante en el cuerpo. Además, ante un informe con formato roto la respuesta era relanzar agentes hasta que el formato saliera bien, de modo que el gate dependía de la suerte, y lo guardado como informe a veces era un resumen posterior que no se puede auditar (PRINCIPLES §10).

## Decisión

El número de bloqueantes sale de un cálculo de `mth` sobre los hallazgos del informe; la línea del agente solo se contrasta. Una discrepancia o un formato ilegible se registran como revisión **fallida** (estado seguro), con un contador de intentos. `mth` archiva el informe literal con el SHA y su huella. Ante un fallo se pide **una** corrección al mismo agente, con su contexto; no se lanza otro desde cero. Detalle en [SPEC-0013](../../features/SPEC-0013-registro-de-revisiones-calculado-por-mth.md).

## Alternativas consideradas

- **Seguir fiándose de la última línea:** el modelo decide el gate; descartada.
- **Calcular y aceptar si el agente discrepa (gana mth):** esconde un informe incoherente, que es señal de que el revisor no ha hecho bien su trabajo; se registra como fallido.
- **Relanzar sin límite hasta que el formato salga bien:** convierte el gate en una lotería; se limita a una corrección y el contador deja ver el problema.
- **Comprobar la corrección de los hallazgos con otro agente:** fuera de alcance; el coste y el problema de confianza se repiten.

## Consecuencias

- El número que decide la integración deja de depender de lo que afirme el modelo.
- Un formato más estricto produce más rechazos al principio: los reintentos y sus motivos quedan visibles, y apuntan a prompts de revisor que hay que corregir.
- Un resumen no sustituye al informe: el archivo literal es el registro.
- Riesgo aceptado: `mth` no valida que la severidad esté bien asignada; sigue siendo juicio del revisor.
