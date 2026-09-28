# Documentos históricos

Acá se guardan los documentos **cerrados**: revisiones, informes y auditorías que
describen el estado del sistema **en una fecha concreta**.

## Cómo funciona

- Los archivos **no se actualizan**. Una vez cerrados, quedan como testimonio de
  lo que se revisó y se decidió ese día.
- Van con la **fecha en el nombre**, en formato `Nombre-AAAA-MM-DD.md`, para que
  se ordenen solos y no haya dudas de a cuándo corresponden.
- Si un documento viejo contradice al código actual, **manda el código** (y el
  `README.md` / `ROADMAP.md`, que sí se mantienen al día).

## Qué NO va acá

- Lo que se mantiene al día (por ejemplo `README.md`, `ROADMAP.md` o
  `GUIA-ANALISTAS.md`) va en la raíz del repositorio, no acá.
- Decidir qué se archiva y cuándo es parte de cerrar una etapa de trabajo: se
  mueve el documento, se le pone la fecha en el nombre y se agrega una línea al
  índice de abajo.

## Índice

| Fecha | Documento | Qué contiene |
|---|---|---|
| 27/09/2026 | [`Review-2026-09-27.md`](Review-2026-09-27.md) | Revisión del sistema: correcciones al informe anterior, OWASP, flujo de revisión, cabeceras de seguridad, tests, endurecimiento, mejoras de gestión y textos legales. Cierra con 121 tests, 93% de cobertura y `ruff` limpio. |
