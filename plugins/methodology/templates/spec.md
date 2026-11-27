# {{ID}} · {{TITLE}}

- Estado: borrador
- Fecha: {{DATE}}
- Formato: compacto
- ADRs: —
- Sustituye a: —
- Seguridad: ninguna

<!-- Seguridad: «ninguna» o la lista de superficies (entrada externa, autenticación, datos sensibles); con superficie, al menos un AC «**AC-NN** [SEG]» con test. -->
<!-- Estados: borrador → aprobada → implementada → sustituida. "implementada" exige un test con `verifies: {{ID}}/AC-NN` por AC.
     Estilo (PRINCIPLES §7): una regla por línea, tablas en lugar de párrafos, referencias por ID, sin introducción ni resumen. -->

## Contexto

Problema y por qué ahora.

## Objetivo

Qué es verdad al terminar.

## Fuera de alcance

- Lo que no se hace.

## Comportamiento

Interfaces y datos, una regla por línea. Enlaza los ADR.

## Modos de fallo

| ID | Causa | Respuesta (estado seguro) | Cubierto por |
|---|---|---|---|
| FM-01 | | | AC-01 |

## Criterios de aceptación

<!-- EARS: CUANDO <disparador>, <sistema> DEBE <respuesta> · SI <condición>, ENTONCES <sistema> DEBE <respuesta>
     · MIENTRAS <estado>, <sistema> DEBE <respuesta> · <sistema> DEBE <respuesta> (permanente) -->

- **AC-01**: CUANDO <disparador>, <sistema> DEBE <respuesta verificable>.

<!-- Si vas a delegar dos o más tareas en agentes dev-*, añade aquí la sección de nivel 2
     "Plan de trabajo" con el formato de la skill mth-spec. -->

## Notas
