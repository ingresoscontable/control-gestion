# Roadmap — Control de Gestión

Documento de trabajo: qué se mejora, en qué orden y con qué criterio se da por terminada
cada fase. Sale del mapeo del sistema hecho el 27/09/2026.

**Regla de oro:** en cada fase se cierra con la suite verde (`pytest tests -q`), `ruff`
sin errores y la documentación (README / GUIA-ANALISTAS.md) actualizada si cambió algo
visible para el usuario. Nada se commitea a medias.

**Fuera de alcance por tamaño del equipo** → están en [Apéndice: Nice-to-have](#apéndice-nice-to-have-no-aplica-hoy).
No se tocan, pero quedan anotados por si el sistema crece.

---

## Avance

| Fase | Estado |
|------|--------|
| 0 — Cimientos | ✅ Hecha (27/09/2026). `ruff check .` limpio, 35 tests en verde, smoke test real con servidor arrancado. |
| 1 — Base de datos | ✅ Hecha (27/09/2026). WAL activo, 3 índices, eager loading verificado con test de conteo de consultas (43 → 5 en la exportación), totales reales, respaldos validados al crear. 42 tests en verde. |
| 2 — Integridad | ✅ Hecha (27/09/2026). Índice único `(usuario_id, fecha, meta_id)` con chequeo previo de duplicados (si hay, los lista en el log y lo deja para después), validación de fecha (hoy − 30 días, `CG_DIAS_ATRASO`), meta ajena rechazada y meta con **borrado lógico** (Archivar/Restaurar). 48 tests en verde. |
| 3 — Seguridad y trazabilidad | ✅ Hecha (27/09/2026). Rate limit 5 intentos / 5 min por IP+usuario con backoff (5→10→20…→30 min), PIN de fábrica redirige a `/ayuda` hasta que se cambie (rutas libres `/ayuda` y `/mi-pin`), tabla `auditoria` firmada por usuario en 11 acciones (incluye crear y restaurar respaldo, manual o automático). 53 tests en verde. |
| 4 — UX y reportes | ✅ Hecha (27/09/2026). Registros paginado de 50 en 50 con filtros recordados (meta, persona, fechas, estado y texto libre) y el Excel bajando todo lo filtrado; PDF mensual por persona desde su ficha; aviso al cargar si se pasa de 8 h/día o 40 h/semana (`CG_HORAS_DIA`, `CG_HORAS_SEMANA`); Excel desde Panel y Persona; página `/auditoria` para el jefe. 59 tests en verde. |
| 5 — Documentación y entrega | ✅ Hecha (27/09/2026). README con **todas** las variables `CG_*` (incluida `CG_HOST`), la sección *Auditoría* y el botón en el menú; GUIA-ANALISTAS con el aviso de carga excesiva y el bloqueo del login. Verificación final: `ruff` limpio, **59 tests**, arranque real con `iniciar.bat` y `data/sistema.log` sin errores. CI verde en GitHub Actions. |
| 6 — Revisión del trabajo | ✅ Hecha (27/09/2026). Flujo jefe ↔ empleado: cada reporte nace `pendiente`, el jefe **aprueba** o **devuelve** con observación, la persona **corrige** y vuelve a revisión. Devolver **reversa el avance** de la meta hasta que se corrija. Filtro por estado de revisión, avisos en el panel, columna en el Excel y 2 acciones nuevas de auditoría. Headers de seguridad HTTP y tests divididos por módulo (`tests/conftest.py` + `test_NN_*.py`). **64 tests** en verde. |
| 7 — Endurecimiento | ✅ Hecha (27/09/2026). **Fuerza bruta lenta cerrada**: los fallos ya no se olvidan por ventana (con `LOGIN_VENTANA=900` y 5 intentos, un ataque de un intento cada 5 min nunca llegaba al límite); ahora se cuentan desde el último acierto y sólo se limpian por inactividad (`LOGIN_OLVIDO`). **Sesiones cortadas al resetear el PIN** (`usuarios.sesion_token`, migración con backfill). Página de **error 500 amigable** con log. Cobertura medida con `pytest-cov` (**93%**, mínimo 90% en CI). **69 tests** en verde. |
| 8 — Mejoras de gestión | ✅ Hecha (27/09/2026). **Días laborables** (`CG_DIAS_LABORABLES`) y **novedades** (vacaciones, licencia, feriado) que bajan el cumplimiento sin marcar a nadie de incumplidor; **cantidad y unidad** por meta (`objetivo`, `unidad`, `Registro.cantidad`) con el avance priorizando cantidad → horas → reportes; **puntualidad** (cargado el mismo día del trabajo) en panel, ficha, Registros y PDF; **informes por rango de fechas libre** con **comparación** contra el período anterior, en pantalla y PDF (`/reportes`), sobre un único motor de PDF (`generar_pdf_rango`, con el mensual como caso particular); **textos legales** públicos en `/legal/*` (privacidad, cookies, términos y licencia) con el pie en la entrada y en todas las páginas, y `LICENSE` MIT. **121 tests** en verde, cobertura **93%**. |

---

## Estado al inicio (27/09/2026)

Punto de partida con el que se armó este roadmap. Lo que ya cambió está en la
tabla de [Avance](#avance).

| Ítem | Estado |
|------|--------|
| Stack | FastAPI 0.115 + Jinja2 (SSR) + SQLAlchemy 2 + SQLite + uvicorn |
| Código | `app/` 2.202 líneas Python, 14 templates, 400 líneas CSS |
| Rutas | 26 en `app/main.py` (1.068 líneas) |
| Tests | 34 en `tests/test_app.py`, todos en verde (hoy: 64 en módulos `test_NN_*.py`) |
| Lint / CI | **No hay** |
| Índices en la base | Solo `usuarios.usuario` |
| Journal mode | Rollback (por defecto) — los escritores bloquean lecturas |
| Auditoría | No hay: se borra y no queda rastro |
| Logging | Loggers declarados, **nadie los configura** |

---

## Fase 0 — Cimientos (higiene y verificación automática)

> Tamaño: **S** (medio día). Objetivo: que todo lo que venga después se verifique solo.

| # | Tarea | Archivo | Detalle |
|---|-------|---------|---------|
| 0.1 | Logging a archivo con rotación | `main.py` (raíz) | `RotatingFileHandler` en `data/sistema.log` (5 MB × 3 copias), nivel INFO. Hoy `backup.py:21` y `migraciones.py:12` tienen loggers que **no escribe nadie**: en modo `iniciar-oculto.vbs` el stderr no llega a ningún lado y un respaldo que falla 30 días es invisible. |
| 0.2 | Dejar visible el aviso de PIN inicial | `seed.py:27` | Hoy hace `logger.warning(... PIN: %s)`. Se mantiene (es el mecanismo para que el jefe sepa su PIN), pero hay que asegurarse de que **el log quede protegido** y anotarlo en README. |
| 0.3 | `ruff` en desarrollo | `requirements-dev.txt`, `pyproject.toml` | Config mínima (línea 100, sin reglas raras). Sirve para cazar cosas gratis en cada fase. |
| 0.4 | CI con GitHub Actions | `.github/workflows/ci.yml` | Push/PR → `pip install -r requirements-dev.txt` + `ruff check .` + `pytest tests -q`. Hoy los tests solo corren si alguien se acuerda. |
| 0.5 | `.env.example` | raíz | Documenta `GH_TOKEN` (uso temporal, ver más abajo) sin valores reales. **`.env` sigue ignorado por git** — ya está en `.gitignore`. |

### Nota sobre credenciales

- El repositorio **no es propio**: `origin` = `github.com/ingresoscontable/control-gestion`
  (owner: **IngresosContable**). Existe además un remoto `fork` = `betobeto00/control-gestion`.
- El `GH_TOKEN` que está en `.env` es **provisional, solo para esta tarea** de
  commit/push. No es un secreto del producto: no se documenta en README ni en GUIA,
  no se copia a ningún archivo commiteable, y se revoca/cambia después de la entrega.
- El push se hace **en bloques completos** (varias fases juntas) y nunca a mitad
  de una tarea rota: GitHub Actions cobra minutos de ejecución mensuales y no
  conviene gastarlos por gusto.

**Criterio de cierre:** `ruff check .` limpio, `pytest` en verde y `data/sistema.log`
escribiendo al arrancar. El workflow de GitHub Actions se valida con el primer push
del bloque correspondiente.

---

## Fase 1 — Base de datos: rendimiento y consistencia

> Tamaño: **M** (1 día). Es lo que más duele con el paso del tiempo y lo más barato de toda la lista.

| # | Tarea | Archivo | Detalle |
|---|-------|---------|---------|
| 1.1 | Índices | `models.py` + `migraciones.py` | `registros(fecha)`, `registros(usuario_id, fecha)`, `metas(estado, fecha_limite)`. Hoy solo `usuarios.usuario` está indexado (models.py:29). Panel, Registros, Calendario y Progreso filtran por esas columnas en cada render. |
| 1.2 | `journal_mode=WAL` + `busy_timeout` | `database.py` | Listener en el engine. Con WAL un lector **nunca** queda bloqueado por un escritor. Es lo que evita el clásico `database is locked` con 5–10 personas cargando a la vez en la LAN. |
| 1.3 | Limpiar `-wal` / `-shm` al restaurar | `backup.py` (`_reemplazar`) | **Obligatorio si va 1.2.** Si se reemplaza `control.db` dejando un `-wal` viejo al lado, SQLite intenta reproducir ese WAL sobre la base nueva → corrupción. Borrar los tres archivos (o los tres en el mismo swap atómico). |
| 1.4 | Eager loading | `main.py` | `selectinload(Registro.usuario)`, `selectinload(Registro.meta)`, `selectinload(Meta.asignado)` en los 4 listados. Hoy `registros.html:83` y `meta_editar.html:82` hacen **1 query por fila**: 500 filas = 500 queries por request. |
| 1.5 | Corregir el total engañoso | `main.py:388, 909` | `registros` se limita a 500 (300 en `/personas/{id}`) y `total_horas` se suma **sobre la lista ya truncada**: el jefe ve un total que no es el total. Dos salidas posibles (elegir en la fase): paginar de verdad **o** contar con `COUNT/SUM` aparte y avisar "mostrando N de M". |
| 1.6 | Validar respaldo al crear | `backup.crear_respaldo` | Hoy `_verificar_sqlite` solo corre **al restaurar**, es decir, cuando ya se necesita. Pasarlo también a la creación automática y a la manual. |

**Riesgos:**
- 1.1 sobre una base con datos viejos: el `CREATE INDEX` falla si ya hay duplicados → correr primero un `SELECT` de duplicados y reportarlos antes de crear el índice único (ver 2.1).
- 1.2 cambia el formato de archivos en disco: avisar en README que pueden aparecer `control.db-wal` y `control.db-shm` (son normales, no borrar a mano).

**Tests nuevos:** respaldo creado pasa `_verificar_sqlite`; un escritor concurrente no
bloquea una lectura (mínimo: probar que las conexiones quedan en WAL con
`PRAGMA journal_mode`); total de horas correcto con más de 500 registros.

**Criterio de cierre:** índices creados, WAL activo, ninguna query N+1 en los listados,
total coherente con lo que muestra la tabla.

---

## Fase 2 — Integridad de los datos de negocio

> Tamaño: **M** (1 día). Evita que entre basura y que se pierda información por un error de pulgar.

| # | Tarea | Archivo | Detalle |
|---|-------|---------|---------|
| 2.1 | Constraint único `(usuario_id, fecha, meta_id)` | `models.py` + `migraciones.py` | Hoy un doble clic o dos "Repetir" seguidos crean duplicados, y el % de avance cuando **no** hay horas estimadas cuenta reportes (`progreso.py:29`) → los duplicados inflan el progreso. Migración: primero listar duplicados existentes, mostrarlos, resolverlos, y recién ahí crear el índice único. |
| 2.2 | Validar que la meta sea visible para quien carga | `main.py:360` | Hoy solo se chequea que la meta **exista**, no que pertenezca al usuario. Con el `meta_id` a mano, un empleado puede cargar contra la meta de otro. Reusar `metas_visibles()`. |
| 2.3 | Proteger "Eliminar meta" | `main.py:689` | Hoy desvincula los registros (`meta_id = None`) y se pierde la asociación para siempre. Alternativas (elegir una): deshabilitar el botón si tiene reportes, o pedir confirmación mostrando el conteo, o pasar a borrado lógico. |
| 2.4 | Rango de fechas al cargar | `main.py:367` | Un empleado puede cargar en el futuro o atrasar 6 meses. Definir la regla de negocio (¿hoy ± N días configurable? ¿hasta 30 días atrás para cargar en diferido?) y validarla. |

**Tests nuevos:** registro duplicado rechazado; empleado no puede usar `meta_id` ajeno;
meta con reportes no se borra sin confirmación; fecha fuera de rango rechazada.

**Criterio de cierre:** la base no admite duplicados ni metas ajenas, y ninguna
operación destruye datos sin avisar.

---

## Fase 3 — Seguridad de acceso y trazabilidad

> Tamaño: **M** (1 día).

| # | Tarea | Archivo | Detalle |
|---|-------|---------|---------|
| 3.1 | Rate limit en `/login` | `security.py` + `main.py` | Contador en memoria por IP + usuario con `threading.Lock` (los endpoints son `def`, corren en threadpool) y backoff progresivo. En LAN igual aplica: PIN de 4 dígitos con usuario `jefe` es fuerza brutable en minutos. ~20 líneas. |
| 3.2 | Forzar cambio de PIN inicial | `security.py` / `main.py` | Hoy el README pide cambiarlo "a mano" y nada lo obliga. Marca en `usuarios` (o comparar con `CG_ADMIN_PIN`) + middleware que redirige a `/ayuda` hasta que cambie. |
| 3.3 | Auditoría | `models.py` (tabla nueva) + puntos de escritura | Tabla `auditoria(usuario_id, accion, objeto_tipo, objeto_id, resumen, fecha)`. Registrar como mínimo: crear/editar/eliminar meta, eliminar registro, cambiar PIN, crear usuario, activar/desactivar, crear y **restaurar** respaldo. Hoy `eliminar_registro` (main.py:530) y `restaurar_respaldo` no dejan rastro alguno — en un sistema de *control de gestión* es la mejora que más valor agrega. Vista simple para el jefe (`/auditoria`) puede ir en la fase 4. |

**Tests nuevos:** login bloqueado tras N intentos; redirect si el PIN sigue inicial;
cada acción crítica deja fila en `auditoria`.

**Criterio de cierre:** no se puede fuerzar el PIN, nadie entra con el PIN de fábrica,
y toda acción destructiva queda firmada.

---

## Fase 4 — UX y reportes

> Tamaño: **M–L** (1–2 días). Va después porque depende de las fases anteriores (índices para paginar bien, auditoría para mostrar quién hizo qué).

| # | Tarea | Archivo | Detalle |
|---|-------|---------|---------|
| 4.1 | Paginación + búsqueda de texto en Registros | `main.py`, `registros.html` | Reemplaza el `.limit(500)` mudo por páginas reales y filtro por texto en `descripcion`. Conservar que la exportación a Excel siga bajando **todo lo filtrado** (limit 5000). |
| 4.2 | Filtros recordados | `main.py` / templates | Que meta/persona/fechas no se pierdan al navegar entre páginas. |
| 4.3 | PDF mensual por persona | `reportes.py` | `_datos_del_mes` y `_tabla` ya existen: es agregar el filtro por `usuario_id` y encabezado con el nombre. El jefe se lo puede mandar a cada una. |
| 4.4 | Alerta de carga excesiva | `metricas.py` / panel | Aviso si alguien cargó >8 h en un día o >40 h en la semana (se calcula sobre lo que ya trae `resumen_semanal`). |
| 4.5 | Exportar Excel desde Panel y Persona | `main.py` | Hoy solo existe en `/registros`. Reusar la función ya extraída. |
| 4.6 | Página de auditoría para el jefe | `main.py`, template nuevo | Tabla simple con filtro por fecha/persona. Cierra lo de 3.3. |

**Criterio de cierre:** el jefe puede encontrar cualquier registro sin scrollear 500
filas, exportar lo que filtra y mandarle a cada persona su PDF.

---

## Fase 5 — Documentación y entrega

> Tamaño: **S** (medio día).

| # | Tarea | Detalle |
|---|-------|---------|
| 5.1 | README | Variables nuevas de las fases 1–4 (`CG_...` de rango de fechas, etc.), nota sobre auditoría. Lo de la Fase 0 (log, primer-ingreso, ruff, CI) ya quedó documentado al hacerla. |
| 5.2 | GUIA-ANALISTAS.md | Solo si cambió algo visible para el equipo. |
| 5.3 | Commit y push | **Un solo commit y un solo push al final**, no uno por fase: GitHub Actions cobra minutos de ejecución mensuales y no conviene gastarlos por gusto. Todo se valida antes en local (`ruff` + `pytest`). Mensaje en el estilo del repo (sin acentos, imperativo: `Agregar indices y modo WAL`). Push a `origin` (IngresosContable) usando el `GH_TOKEN` de `.env`. |
| 5.4 | Verificación final | `ruff check .` + `pytest tests -v` + arranque real con `iniciar.bat` + revisar `data/sistema.log`. |

---

## Resumen de esfuerzo

| Fase | Contenido | Tamaño | Acumulado |
|------|-----------|--------|-----------|
| 0 | Logging, ruff, CI, `.env.example` | S | medio día |
| 1 | Índices, WAL, eager loading, totales, respaldos | M | ~1,5 días |
| 2 | Integridad: duplicados, metas ajenas, borrar, fechas | M | ~2,5 días |
| 3 | Rate limit, PIN inicial, auditoría | M | ~3,5 días |
| 4 | Paginación, búsqueda, PDF por persona, alertas | M–L | ~5 días |
| 5 | Docs y push final | S | ~5,5 días |

---

## Apéndice: Nice-to-have (no aplica hoy)

Anotados por si el sistema crece. **No entran en ninguna fase.**

| Idea | Por qué no aplica ahora |
|------|--------------------------|
| Rol intermedio "supervisor" | Solo hay jefe + empleados; agregar un rol implica tocar todos los `requiere_jefe` y los menús. |
| Notificaciones externas (correo/WhatsApp) | El sistema es offline por diseño: sin internet ni servidores externos. El aviso de meta vencida ya está en el panel. |
| HTTPS / TLS | Red interna de confianza, ya documentado en README. Solo si algún día se expone fuera de la LAN. |
| Multi-empresa / multi-sede | Es una oficina chica con una sola base `control.db`. |
| Borrado lógico global (soft delete) en todas las entidades | Solo hace falta donde hoy se destruye data sin rastro; ya está cubierto en 2.3 y 3.3. |
| Redis / caché de panel | SQLite + índices alcanza de sobra para el volumen real. |
| Tema oscuro / responsive móvil | Nadie lo pidió; la UI está hecha a propósito para Chrome 109 en Win7. |
| SSO / LDAP / 2FA | El equipo entra con usuario + PIN en una red cerrada. |
| Dividir `app/main.py` en routers (1.068 líneas) | Estético. Conviene **cuando se toque ese archivo por otra razón**, no como fase propia. |
| Alembic en lugar de `migraciones.py` | Las 5 migraciones que hace hoy el sistema propio son más simples de leer que un setup de Alembic. |
| Índice de texto (FTS5) para buscar en las descripciones | La búsqueda usa `LIKE '%texto%'` con comodín inicial: **ningún índice puede usarlo**, siempre escanea. Con el volumen real (miles de filas, 3 personas) ni se nota, y una tabla FTS5 + triggers + migración es mucho mantenimiento para cero beneficio hoy. |
