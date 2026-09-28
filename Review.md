# Review — Control de Gestión

**Fecha:** 27 de septiembre de 2026
**Repositorio:** control-gestion (`main`)
**Alcance:** revisión del informe anterior + verificación real contra el código
**Método:** lectura del código, `ruff check .` y `pytest tests -q`

---

## Veredicto

El informe anterior describía bien el sistema en general, pero **contenía
afirmaciones falsas y números de línea inventados** en la parte del archivo de
pruebas, y **recomendaba medidas que conviene no aplicar** (bloquear F12, el
clic derecho y la selección de texto). Esta versión reemplaza esas partes por lo
que dice el código.

**Estado del proyecto:** ✅ `ruff` limpio, **69 tests en verde**, cobertura **93%**.

---

## 1. Correcciones al informe anterior

| Afirmación del informe | Qué dice el código |
|---|---|
| A3 · "Uso exclusivo de SQLAlchemy ORM (**sin SQL raw**)" | **Falso.** Hay SQL literal en `app/database.py:29-30` (`PRAGMA journal_mode`, `busy_timeout`), `app/backup.py:65,73` (`PRAGMA integrity_check`, `SELECT name FROM sqlite_master`) y en todo `app/migraciones.py` (`exec_driver_sql`). No es inyectable: son sentencias fijas, sin datos del usuario. La conclusión (no hay injection) es correcta; la justificación no. |
| A6 · "Dependencias actualizadas ✅ CUMPLE" | **Optimista.** `fastapi==0.115.6`, `uvicorn==0.34.0` y `sqlalchemy==2.0.36` son de fines de 2024 (~21 meses antes de esta fecha). Están *fijadas*, no *actualizadas*. |
| Sección 5 · rangos de líneas del test | **Inventados.** Decía "filtrado 652-750" (el test real está en 885), "calendario 752-820" (real 1091), "auditoría 922-1030" (real 1581+), "índices 1535-1580" (real 1155+). |
| Sección 5 · "Todo el suite se ejecuta siempre / difícil de paralelizar" | **Impreciso.** pytest permite `-k`, `--deselect` y correr un archivo suelto; los 64 tests tardan ~13 s. |
| Resumen ejecutivo · "Sistema monolítico" | **Falso.** `app/` son 13 módulos (3.328 líneas). El único archivo grande es `app/main.py` (1.703 líneas), que es la capa de rutas. El propio informe lo llamaba "arquitectura limpia y modular" dos párrafos antes. |
| Sección 4 · "Este sistema es ~0,001% del tráfico de una llamada VoIP" | **Mal calculado.** 3,6 MB/día ≈ 0,042 KB/s contra ~50 KB/s de VoIP ≈ **0,08%**, no 0,001% (80× menos de lo que decía). |
| Sección 4 · "`style.css`: 12.070 bytes" | Era correcto entonces; hoy son **12.761 bytes** (se agregaron estilos de revisión). |

### Recomendaciones que NO hay que aplicar

**Sección 3 (bloquear F12 / clic derecho / selección de texto).** Se descartó:

- Contradice el diseño declarado en el README ("nada de JavaScript moderno, sólo
  `confirm()` nativos") hecho por compatibilidad con **Chrome 109 en Windows 7**.
- Es *security theater*: se saltea en segundos, y lo único que logra es impedir
  que alguien copie sus propios datos para trabajar.
- El `ScrapingProtection` propuesto **duplicaba** `LimitadorDeIntentos`, que ya
  existe en `app/security.py:65`.

En su lugar se implementaron **cabeceras HTTP reales** (ver §5), que el navegador
sí respeta.

**Sección 6 (código propuesto de reversión).** Traía dos errores:

1. `revertir_registro` asignaba `registro.estado = "revertido"`, que **no está en
   `ESTADOS_REGISTRO`** → habría roto el filtro por estado y la insignia.
2. `corregir_registro` ignoraba el índice único `(usuario_id, fecha, meta_id)`
   agregado en la Fase 2.

La funcionalidad **sí se implementó**, con un diseño distinto que se apoya en el
estado de revisión en vez de en `estado` (ver §4).

---

## 2. Estado verificado del sistema

| Ítem | Valor |
|---|---|
| Stack | FastAPI 0.115 + Jinja2 (SSR) + SQLAlchemy 2 + SQLite (WAL) + uvicorn |
| Rutas | 35 en `app/main.py` (1.728 líneas) |
| Código | `app/` 3.353 líneas Python, 18 templates, `style.css` 12.761 bytes |
| Tests | **69** en 14 módulos `tests/test_NN_*.py` + `conftest.py` + `helpers.py` |
| Cobertura | **93%** medida con `pytest-cov`; CI exige mínimo 90% |
| Lint / CI | `ruff` limpio; GitHub Actions corre `ruff check .` + `pytest --cov` |
| Índices | `registros(fecha)`, `registros(usuario_id, fecha)`, `registros(estado_revision)`, único `(usuario_id, fecha, meta_id)`, `metas(estado, fecha_limite)`, `auditoria(fecha)` |
| Journal | WAL + `busy_timeout=5000` |
| Auditoría | 13 acciones firmadas por usuario |

---

## 3. OWASP (corregido)

| Categoría | Estado | Nota |
|---|---|---|
| A1 · Broken Access Control | ✅ | `requiere_login` (`main.py:149`), `requiere_jefe` (`main.py:163`), verificación de propiedad al eliminar, corregir y revisar. |
| A2 · Cryptographic Failures | ✅ | PBKDF2-SHA256, 120.000 iteraciones (`security.py:18`), salt de 16 bytes, `hmac.compare_digest` (`security.py:42`). `SECRET_KEY` autogenerada en `data/.secret_key`. |
| A3 · Injection | ✅ | Sin SQL construido con datos del usuario; el SQL literal existente es fijo. `ilike` parametrizado para el texto libre. |
| A4 · Insecure Design | ✅ | ~~Faltaba el flujo de revisión~~ → **implementado** (§4). Fecha validada (hoy − `CG_DIAS_ATRASO`), futuro rechazado, duplicados bloqueados. |
| A5 · Security Misconfiguration | ✅ | ~~Sin cabeceras~~ → **implementadas** (§5). ~~Sin protección de devtools~~ → se decidió **no** bloquearlas (ver arriba). WAL activo. |
| A6 · Componentes desactualizados | ⚠️ | Versiones fijadas y estables, pero **no** recientes. Actualizar es una tarea aparte, con regresión de tests. |
| A7 · Fallas de autenticación | ✅ | Rate limit por IP+usuario con backoff exponencial hasta 30 min (`security.py:65`). Los fallos **no se olvidan con el tiempo** (antes, con ventana de 15 min, un ataque de un intento cada 5 min nunca llegaba al límite); el contador sólo se limpia por inactividad. Sesiones cortadas al resetear el PIN. PIN 4-10 dígitos (`security.py:56`). PIN de fábrica obliga a cambiarlo (`security.py:139`). |
| A8 · Integridad de datos | ✅ | Respaldos con `integrity_check` **al crear y al restaurar**; limpieza de `-wal`/`-shm` al restaurar. |
| A9 · Logging y monitorización | ✅ | `data/sistema.log` con rotación (5 MB × 3) en `main.py:26`; tabla `auditoria`; los errores 500 quedan en el log y el usuario ve una página amigable. |
| A10 · SSRF | ✅ No aplica | Sin llamadas salientes. |

---

## 4. Flujo de revisión (implementado)

Cada reporte tiene `estado_revision`: `pendiente` → `aprobado` |
`correccion_pendiente` → (al corregir) `pendiente`.

- `POST /registros/{id}/revisar` (`main.py:944`, sólo jefe) — aprueba o devuelve
  con observación obligatoria. Devolver **reversa el avance**: `app/progreso.py`
  excluye los reportes `correccion_pendiente`, así que una meta puede bajar de %.
- `GET/POST /registros/{id}/corregir` (`main.py:991,1016`) — el dueño (o el jefe)
  corrige descripción, horas y estado; el reporte vuelve a `pendiente`.
- Filtro por estado de revisión en `/registros`, columna nueva en el Excel,
  avisos en el panel (para el jefe y para la persona) y 2 acciones de auditoría
  (`revisar_registro`, `corregir_registro`).
- Migración automática en `app/migraciones.py` para bases ya instaladas.

---

## 5. Cabeceras de seguridad (implementado)

Middleware `headers_de_seguridad` (`main.py:97`) que agrega a toda respuesta:

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`,
`X-Robots-Tag: noindex, nofollow, nosnippet, noarchive`.

No se agregó `X-XSS-Protection` (obsoleto y puede introducir problemas).

---

## 6. Tests (refactorizado)

`tests/test_app.py` (2.030 líneas) se dividió en:

```
tests/
├── conftest.py   # CG_DATA_DIR, CG_SECRET_KEY y fixture client
├── helpers.py    # login e id_* compartidos
└── test_01_auth.py … test_14_revision.py
```

Los archivos van **numerados a propósito**: comparten la misma base durante toda
la corrida y algunos se apoyan en datos que cargaron los anteriores. El nuevo
`test_14_revision.py` es autocontenido (crea su propio empleado), así que se puede
correr solo con `pytest tests/test_14_revision.py`. La cobertura global es 93%
(mínimo exigido en CI: 90%).

**Nota:** los módulos 01–13 siguen dependiendo del orden. Hacerlos todos
independientes requiere mover la creación de datos base a fixtures y es una
tarea pendiente, no un cambio cosmético.

---

## 7. Red con 3 usuarios

Sin cambios respecto del informe anterior, salvo la corrección de la proporción
frente a VoIP. El sistema es SSR sobre HTTP plano, con SQLite local: no hay
tráfico entre clientes ni consultas por red. Con 3 usuarios la carga es
despreciable (estimación: ~3,6 MB/día ≈ 0,042 KB/s, ~0,08% de una llamada VoIP).

Se sigue recomendando **no** optimizar red.

---

## 8. Endurecimiento aplicado (27/09/2026)

1. **Fuerza bruta lenta cerrada.** Antes el conteo sólo miraba los últimos
   15 min, así que un intento cada 5 min nunca llegaba a 5 y el bloqueo no se
   activaba nunca. Ahora los fallos se cuentan desde el último acierto y el
   diccionario sólo se limpia por inactividad (`LOGIN_OLVIDO`, 24 h).
2. **Sesiones cortadas al resetear el PIN.** `usuarios.sesion_token` (columna
   nueva, con migración y backfill) viaja en la cookie; al resetear un PIN o al
   cambiar el propio se renueva. Cambiar el PIN propio **no** saca al que lo
   cambió. Resuelve el hueco de que la cookie vieja siguiera válida 14 días.
3. **Página de error 500 amigable.** Antes sólo había handler para
   `Redireccionar`. Ahora cualquier excepción no controlada se loguea y muestra
   una página con el estilo del sistema.
4. **Cobertura medida y exigida.** `pytest-cov` mide `app/` (93%) y el CI falla
   por debajo del 90%.

## 9. Pendientes sugeridos (no urgentes)

1. **Actualizar dependencias** (A6) con la suite como red de seguridad.
2. **Independizar los tests 01–13** del orden de ejecución vía fixtures.
3. **Dividir `app/main.py`** (1.728 líneas) en routers. Es estético; conviene
   hacerlo cuando se toque ese archivo por otra razón, no como tarea propia.
4. **Búsqueda de texto con índice (FTS5).** Hoy es `LIKE '%texto%'`, que ningún
   índice puede usar; con el volumen real no se nota.
5. **PIN mínimo de 6 dígitos.** El mínimo actual son 4, que es lo que hacía
   viable la fuerza bruta; con el limitador arreglado deja de ser urgente, y
   subirlo cambia la UX y el PIN de fábrica (`1234`).
6. **CSP** sólo si algún día se expone fuera de la LAN.

---

**Review realizado con verificación automática** (`ruff` + `pytest`)
**Revisión siguiente sugerida:** al actualizar dependencias o al sumar un rol nuevo.
