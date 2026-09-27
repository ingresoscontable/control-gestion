# Control de Gestión

Sistema interno y sencillo para el control de gestión de una oficina pequeña.
Corre en **una sola PC de la oficina** y los demás entran desde su navegador por
la **red local** (no requiere internet ni servidores externos).

- El **jefe** crea las metas del equipo y revisa todo.
- Cada **empleado** entra con su usuario y PIN, ve las metas que le tocan y
  registra a diario lo que hizo (descripción, horas y estado).
- Todo se guarda en un único archivo SQLite: `data/control.db`.

---

## Requisitos

- Windows 10 (también funciona en Linux/Mac).
- Python 3.10 o superior. Descarga: <https://www.python.org/downloads/windows/>
  - **Importante:** al instalar, marcar la casilla **"Add python.exe to PATH"**.

---

## Instalación en Windows 10 (PC principal)

1. Copia esta carpeta a la PC que hará de servidor (por ejemplo `C:\ControlGestion`).
2. Doble clic en **`instalar.bat`**. Crea el entorno virtual e instala las dependencias.
3. Doble clic en **`abrir-firewall.bat`** (clic derecho → *Ejecutar como administrador*).
   Esto abre el puerto 8000 en la red local. **Se hace una sola vez.**
4. Doble clic en **`iniciar.bat`**.

Al arrancar verás algo así:

```
================================================================
  Control de Gestion - servidor de la oficina
================================================================
  En esta PC:   http://localhost:8000
  Otras PC:     http://192.168.1.25:8000
----------------------------------------------------------------
```

Deja esa ventana abierta: mientras esté abierta, el sistema está disponible.
Si Windows pregunta por el acceso a la red, marca **Redes privadas** y acepta.

**¿Prefieres no dejar la ventana abierta?** Doble clic en **`iniciar-oculto.vbs`**:
el servidor queda corriendo en segundo plano, sin ninguna ventana visible
(aparece un mensaje de confirmación y ya). Para detenerlo, doble clic en
**`detener.bat`**. El sistema sigue disponible para las demás PC mientras esté corriendo.

**¿Querés que arranque solo cada vez que prendés la PC?** Doble clic en
**`instalar-arranque.bat`**. Cada vez que inicies sesión en Windows, el servidor
arranca solo en segundo plano, sin ventana ni mensaje. No hace falta
administrador. Para desactivarlo, **`desinstalar-arranque.bat`**
(el que ya esté corriendo sigue corriendo hasta que uses `detener.bat`).

### Primer ingreso

| Usuario | PIN  |
|---------|------|
| `jefe`  | `1234` |

Entra y **cambia el PIN de inmediato** en la sección *Ayuda → Cambiar mi PIN*.
**Ya no es opcional**: mientras el PIN siga siendo el de fábrica, el sistema no
te deja pasar de la pantalla de Ayuda.

Mientras no lo cambies, las credenciales quedan escritas en
`data/primer-ingreso.txt` por si las necesitás volver a leer. **Ese archivo se
borra solo** en cuanto el jefe cambia su PIN.

---

## Uso desde las otras PC

1. Abre Chrome o Edge.
2. Escribe la dirección que apareció como *Otras PC*, por ejemplo
   `http://192.168.1.25:8000`.
3. Inicia sesión con el usuario y PIN que te dio el jefe.

> Si la IP de la PC cambia (por ejemplo al reiniciar el router), vuelve a mirar
> la ventana negra al arrancar, o entra al sistema y abre la página **Ayuda**,
> que siempre muestra las direcciones actuales.

---

## Día a día

**Jefe**

- *Equipo* → crear un acceso por persona (analista contable, liquidadora, etc.).
- *Metas* → crear la meta, asignarla a una persona o a todo el equipo, ponerle
  fecha límite y (opcional) **horas estimadas** de trabajo. Cualquier meta se
  puede **editar después** (título, responsable, plazo, horas estimadas y
  estado) desde el botón *Editar*, sin perder los reportes ya cargados.
  El botón *Duplicar* hace una **copia de la meta** (título, responsable, plazo
  y horas) y abre el formulario para ajustarla: sirve para repetir la
  estructura del corte anterior sin volver a cargar todo a mano. La copia
  arranca siempre activa, aunque el original esté cerrado.
  El botón **Archivar** no borra la meta: la saca de las pantallas y de los
  reportes pero **conserva todos sus reportes**, y se revierte con **Restaurar**
  (o desde *Editar*, llevando el estado a *Activa*).
- *Progreso* → vista con barra de avance por meta, más el promedio y las horas
  acumuladas del equipo.
- *Panel* → ver quién ya registró hoy y quién falta; ver el avance de cada meta
  y el **resumen de la semana** por persona (registros, días reportados y horas).
  Arriba aparece un **aviso en rojo cuando una meta activa pasó su fecha
  límite**, con los días de atraso (al equipo le muestra solo las suyas).
  Cierra el panel con un **gráfico de horas de las últimas 8 semanas**, una barra
  por persona y por semana.
- *Registros* → historial completo **paginado de 50 en 50**, con filtros por
  **meta**, persona, rango de fechas, **estado** del reporte y **texto libre
  dentro de la descripción**. Los filtros se recuerdan al pasar de página y al
  exportar. El botón **Exportar a Excel** baja a `.xlsx` exactamente lo que está
  filtrado (todos, no la página), y hay **reporte mensual en PDF** con resumen
  general, resumen por persona, metas del periodo y detalle de los reportes
  diarios.
- *Calendario* → el mes en curso dibujado día por día: quién cargó, con cuántas
  horas y quién no reportó. Flechas para pasar al mes anterior o siguiente.
- *Comentarios* → en el panel y en registros puedes dejarle una observación a
  cada reporte diario (el empleado la ve, pero no puede editarla).
- *Respaldos* → copia de seguridad automática (cada 24 h y al arrancar) y botón
  para hacer una a mano. Los respaldos viejos se borran solos.
- *Auditoría* → quién hizo qué y cuándo: meta creada, archivada o editada,
  reporte eliminado o comentado, usuario creado o bloqueado, PIN cambiado,
  respaldo creado o restaurado. Filtrable por persona, acción y fecha.
- *Personas* → haz clic en cualquier nombre (en *Equipo*, en *Registros* o en el
  panel) y ves su **historial completo**: todos sus reportes, sus metas con el
  avance y los comentarios que le dejaste, con filtro por fechas. Desde ahí
  también salen el **Excel** de esa persona y su **PDF mensual**, listo para
  enviárselo.

**Empleado**

- *Panel* → elegir la meta, escribir lo que hizo, las horas y el estado, y guardar.
  También ve **el avance de sus metas** con la barra de progreso.
  Se puede cargar **desde hace 30 días hasta hoy** (ajustable con
  `CG_DIAS_ATRASO`) y **un solo reporte por día y por meta**: si ya cargaste,
  editá o borrá el anterior en lugar de duplicarlo.
  En *Mis últimos registros* cada fila tiene un enlace **Repetir**: precarga el
  formulario con esa carga (meta, descripción, horas y estado) pero con la fecha
  de hoy, para no volver a escribir lo mismo todos los días.
  Si al guardar te aparece un **aviso de carga excesiva** (más de 8 h en un día
  o 40 en la semana) es solo un cartel para revisarlo: **el reporte se guarda
  igual**.

---

## Guía para el equipo

Hay un instructivo corto en dos lugares:

- **Dentro del sistema**: el enlace *Guía* del menú superior (`/guia`), que ya
  muestra la dirección correcta para entrar. Es lo que conviene mandarle a las
  analistas: no tienen que abrir ningún archivo.
- **Para imprimir o enviar**: [`GUIA-ANALISTAS.md`](GUIA-ANALISTAS.md) en esta
  misma carpeta.

---

## Respaldo (importante)

Toda la información vive en **`data/control.db`**. El sistema ya hace respaldos
solo: uno al arrancar y otro cada 24 horas, en `data/respaldos/`, conservando
los últimos 30. Revisa la página **Respaldos** para ver el estado y crear uno a
mano.

> **Archivos `control.db-wal` y `control.db-shm`:** pueden aparecer al lado de la
> base. Son parte del modo de escritura de SQLite (WAL), que el sistema usa para
> que quien está leyendo no se quede esperando a quien está cargando datos.
> **No los borres a mano**: el sistema los gestiona y los limpia cuando restaura.

**Restaurar:** en la página **Respaldos**, cada archivo tiene un botón
*Restaurar*. Vuelve la base al estado de ese momento. Antes de reemplazarla el
sistema deja una copia de seguridad del estado actual (etiqueta
`antes-de-restaurar`), así que también se puede volver a esa copia. Si en ese
exacto momento alguien está cargando datos, el sistema espera un par de
segundos y te avisa para que lo repitas.

**Ojo con el disco:** por defecto los respaldos quedan en `data/respaldos/`,
es decir, **en el mismo disco que la base**. Si se rompe el disco se pierde todo
junto. La página **Respaldos** muestra un aviso en ese caso. Para guardarlo en
otro lado (pendrive o carpeta de red) apuntá `CG_BACKUP_DIR` ahí. Aun así,
conviene copiar esa carpeta a un pendrive o a la nube de vez en cuando.

---

## Registro de eventos (log)

El sistema escribe su actividad en **`data/sistema.log`**: arranques, respaldos
creados o fallidos, migraciones aplicadas. Gira solo (5 MB × 3 copias) y no
crece sin límite.

Si el servidor corre oculto (`iniciar-oculto.vbs`), **este archivo es la única
pista** de que un respaldo automático dejó de funcionar: conviene mirarlo de vez
en cuando. Para más detalle, la variable `CG_LOG_LEVEL=DEBUG`.

---

## Auditoría (quién hizo qué)

Además del log, el sistema guarda en la base una **tabla `auditoria`** con cada
acción que cambia información:

| Qué queda registrado | Ejemplo de fila |
|----------------------|-----------------|
| Crear / editar / archivar una meta | `crear_meta`, `editar_meta`, `archivar_meta` |
| Duplicar una meta | `duplicar_meta` |
| Eliminar un reporte | `eliminar_registro` |
| Dejar (o borrar) un comentario en un reporte | `comentar_registro` |
| Crear usuario, activar/desactivar, cambiarle el PIN | `crear_usuario`, `cambiar_estado_usuario`, `cambiar_pin` |
| Cambiar mi propio PIN | `cambiar_pin` |
| Crear y **restaurar** un respaldo (manual o automático) | `crear_respaldo`, `restaurar_respaldo` |

Cada fila guarda **quién** lo hizo (o vacío si fue el sistema), **qué** acción,
**sobre qué** objeto y una frase resumen, con fecha. Se escribe en la misma
transacción que la acción: si algo falló, no queda registrada como hecho; y si
se restaura un respaldo viejo, la fila se escribe **después** del restore, así
que no se pierde.

El detalle está en la página **Auditoría** del menú superior (`/auditoria`),
con filtros por persona, acción y fecha. Solo la ve el jefe.

---

## Configuración opcional

Se puede ajustar sin tocar el código, creando variables de entorno en Windows
(*Configuración → Sistema → Acerca de → Configuración avanzada del sistema →
Variables de entorno*) o editando `iniciar.bat`:

| Variable            | Por defecto                  | Para qué sirve                       |
|---------------------|------------------------------|--------------------------------------|
| `CG_PORT`           | `8000`                       | Puerto del servidor                  |
| `CG_HOST`           | `0.0.0.0`                    | Dirección en la que escucha. `0.0.0.0` lo deja visible en la red local; poné una IP propia si la PC tiene varias. |
| `CG_SECRET_KEY`     | (se genera sola)             | Clave que firma la sesión. Si no se define, cada instalación genera la suya y la guarda en `data/.secret_key`; definila a mano solo si querés controlarlo vos. |
| `CG_DATA_DIR`       | `./data`                     | Carpeta del archivo de base de datos |
| `CG_ADMIN_USUARIO`  | `jefe`                       | Usuario inicial del jefe             |
| `CG_ADMIN_PIN`      | `1234`                       | PIN inicial (solo en el primer arranque) |
| `CG_ADMIN_NOMBRE`   | `Jefe de División`           | Nombre mostrado del jefe             |
| `CG_BACKUP_DIR`     | `./data/respaldos`           | Carpeta de respaldos (puede ser un pendrive o carpeta de red) |
| `CG_BACKUP_HORAS`   | `24`                         | Cada cuántas horas se respalda       |
| `CG_BACKUP_CONSERVAR` | `30`                       | Cuántos respaldos se conservan       |
| `CG_LOG_LEVEL`      | `INFO`                      | Nivel del log del sistema (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CG_DIAS_ATRASO`    | `30`                        | Cuántos días hacia atrás se puede cargar un reporte (`0` = solo hoy) |
| `CG_HORAS_DIA`      | `8`                         | Horas en un día a partir de las cuales aparece el aviso de carga excesiva |
| `CG_HORAS_SEMANA`   | `40`                        | Horas en la semana a partir de las cuales aparece el aviso (aviso, no bloquea) |

Ejemplo para guardar los respaldos en un pendrive, dentro de `iniciar.bat`:

```bat
set CG_BACKUP_DIR=D:\Respaldos\ControlGestion
call ".venv\Scripts\python.exe" main.py
```

> **Nota:** el programa **no** lee archivos `.env`: las variables tienen que
> estar en el entorno de Windows o en `iniciar.bat`. Un `.env` en la raíz se usa
> solo para herramientas de desarrollo y está ignorado por git (ver
> `.gitignore`).

---

## Estructura del proyecto

```
control-gestion/
├── main.py                 # arranque del servidor
├── pyproject.toml          # configuración del analizador de código (ruff)
├── .github/workflows/      # pruebas automáticas en cada push
├── instalar.bat            # instalación en Windows
├── iniciar.bat             # arranque en Windows (con ventana)
├── iniciar-oculto.vbs      # arranque en segundo plano (sin ventana)
├── detener.bat             # detiene el servidor en segundo plano
├── instalar-arranque.bat   # hace que arranque solo al iniciar sesion
├── desinstalar-arranque.bat # quita ese arranque automatico
├── abrir-firewall.bat      # abre el puerto en la red local (admin)
├── app/
│   ├── main.py             # rutas y lógica
│   ├── models.py           # usuarios, metas, registros y auditoría
│   ├── database.py         # SQLite
│   ├── security.py         # hash de PIN, detección de IP y bloqueo de login
│   ├── auditoria.py        # deja registro de quién hizo cada cambio
│   ├── reportes.py         # reportes mensuales en PDF (general y por persona)
│   ├── progreso.py         # cálculo del avance de las metas
│   ├── metricas.py         # resumen semanal, gráfico de horas y calendario
│   ├── backup.py           # respaldos automáticos y manuales
│   ├── migraciones.py      # agrega columnas nuevas a bases ya existentes
│   ├── seed.py             # crea el usuario jefe la primera vez
│   ├── templates/          # páginas HTML
│   └── static/style.css
├── tests/                  # pruebas automáticas
└── data/control.db         # la base de datos (se crea sola)
```

---

## ¿Y las PCs con Windows 7?

No hay problema **mientras el servidor corra en Windows 10**: las otras PCs solo
necesitan un navegador, no instalan nada.

Lo que sí hay que cuidar es el navegador del cliente. En Windows 7 Chrome y Edge
se quedaron en la **versión 109**, así que la interfaz se hizo a propósito con:

- CSS simple: flexbox, `display: grid` a dos o tres columnas y variables de
  color. Nada de `:has()` ni de funciones nuevas del CSS.
- Nada de JavaScript moderno: solo `confirm()` nativos en los botones que
  borran o duplican algo.
- **Sin emojis**, porque Windows 7 no trae la fuente de emoji (Segoe UI Emoji
  llegó con Windows 8) y se verían como cuadraditos.

Si en cambio necesitás correr el **servidor** en Windows 7, eso sí es complicado:
Windows 7 solo soporta hasta Python 3.8.10, y este proyecto pide `uvicorn 0.34` y
`pydantic 2.13`, que necesitan Python 3.9+. Habría que fijar versiones anteriores
y ajustar anotaciones del código. Avisame y armo esa variante.

## Pruebas y chequeos (desarrollo)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
.venv/bin/python -m pip install -r requirements-dev.txt       # Linux/Mac
.venv/Scripts/python -m pytest tests -v                       # Windows
.venv/bin/python -m pytest tests -v                           # Linux/Mac
.venv/Scripts/ruff check .                                    # analizador de código
```

Las mismas dos comandas corren solas en GitHub Actions con cada push
(`.github/workflows/ci.yml`).

---

## Notas de seguridad

Esta herramienta está pensada para una **red interna de confianza**. El login es
usuario + PIN (guardado con PBKDF2, nunca en texto plano), pero no incluye
HTTPS. No la expongas directamente a internet.

Lo que sí está cubierto:

- **Intentos de PIN:** 5 fallos por IP + usuario en 5 minutos bloquean el login
  con un aviso, y el bloqueo crece (5, 10, 20… hasta 30 minutos) si sigue
  insistiendo. Cualquier otra persona sigue pudiendo entrar mientras tanto.
- **PIN de fábrica:** nadie queda logueado con el PIN inicial: hasta que lo
  cambie, solo puede ver *Ayuda* y *Cambiar mi PIN*.
- **Trazabilidad:** toda acción que borra o modifica información queda en la
  tabla `auditoria` (ver [Auditoría](#auditoría-quién-hizo-qué)).
