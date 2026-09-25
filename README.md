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

### Primer ingreso

| Usuario | PIN  |
|---------|------|
| `jefe`  | `1234` |

Entra y **cambia el PIN de inmediato** en la sección *Ayuda → Cambiar mi PIN*.

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
- *Progreso* → vista con barra de avance por meta, más el promedio y las horas
  acumuladas del equipo.
- *Panel* → ver quién ya registró hoy y quién falta; ver el avance de cada meta
  y el **resumen de la semana** por persona (registros, días reportados y horas).
  Arriba aparece un **aviso en rojo cuando una meta activa pasó su fecha
  límite**, con los días de atraso (al equipo le muestra solo las suyas).
  Cierra el panel con un **gráfico de horas de las últimas 8 semanas**, una barra
  por persona y por semana.
- *Registros* → historial completo, con filtros por persona y rango de fechas,
  botón **Exportar a Excel** que baja a `.xlsx` exactamente lo que está filtrado,
  y **reporte mensual en PDF** con resumen general, resumen por persona, metas
  del periodo y detalle de los reportes diarios.
- *Comentarios* → en el panel y en registros puedes dejarle una observación a
  cada reporte diario (el empleado la ve, pero no puede editarla).
- *Respaldos* → copia de seguridad automática (cada 24 h y al arrancar) y botón
  para hacer una a mano. Los respaldos viejos se borran solos.
- *Personas* → haz clic en cualquier nombre (en *Equipo*, en *Registros* o en el
  panel) y ves su **historial completo**: todos sus reportes, sus metas con el
  avance y los comentarios que le dejaste, con filtro por fechas.

**Empleado**

- *Panel* → elegir la meta, escribir lo que hizo, las horas y el estado, y guardar.
  También ve **el avance de sus metas** con la barra de progreso.

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
mano. Aun así, conviene copiar esa carpeta a un pendrive o a la nube de vez en
cuando (o apuntar `CG_BACKUP_DIR` directamente a un pendrive).

---

## Configuración opcional

Se puede ajustar sin tocar el código, creando variables de entorno en Windows
(*Configuración → Sistema → Acerca de → Configuración avanzada del sistema →
Variables de entorno*) o editando `iniciar.bat`:

| Variable            | Por defecto                  | Para qué sirve                       |
|---------------------|------------------------------|--------------------------------------|
| `CG_PORT`           | `8000`                       | Puerto del servidor                  |
| `CG_SECRET_KEY`     | `cambiar-esta-clave-...`     | Clave que firma la sesión (cámbiala) |
| `CG_DATA_DIR`       | `./data`                     | Carpeta del archivo de base de datos |
| `CG_ADMIN_USUARIO`  | `jefe`                       | Usuario inicial del jefe             |
| `CG_ADMIN_PIN`      | `1234`                       | PIN inicial (solo en el primer arranque) |
| `CG_ADMIN_NOMBRE`   | `Jefe de División`           | Nombre mostrado del jefe             |
| `CG_BACKUP_DIR`     | `./data/respaldos`           | Carpeta de respaldos (puede ser un pendrive o carpeta de red) |
| `CG_BACKUP_HORAS`   | `24`                         | Cada cuántas horas se respalda       |
| `CG_BACKUP_CONSERVAR` | `30`                       | Cuántos respaldos se conservan       |

Ejemplo para guardar los respaldos en un pendrive, dentro de `iniciar.bat`:

```bat
set CG_BACKUP_DIR=D:\Respaldos\ControlGestion
call ".venv\Scripts\python.exe" main.py
```

---

## Estructura del proyecto

```
control-gestion/
├── main.py                 # arranque del servidor
├── instalar.bat            # instalación en Windows
├── iniciar.bat             # arranque en Windows (con ventana)
├── iniciar-oculto.vbs      # arranque en segundo plano (sin ventana)
├── detener.bat             # detiene el servidor en segundo plano
├── abrir-firewall.bat      # abre el puerto en la red local (admin)
├── app/
│   ├── main.py             # rutas y lógica
│   ├── models.py           # usuarios, metas, registros
│   ├── database.py         # SQLite
│   ├── security.py         # hash de PIN y detección de IP
│   ├── reportes.py         # reporte mensual en PDF
│   ├── progreso.py         # cálculo del avance de las metas
│   ├── metricas.py         # resumen semanal y gráfico de horas
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

- CSS simple (flexbox y variables de color), sin `grid` avanzado ni `:has()`.
- Nada de JavaScript moderno: el único JS son dos `confirm()`.
- **Sin emojis**, porque Windows 7 no trae la fuente de emoji (Segoe UI Emoji
  llegó con Windows 8) y se verían como cuadraditos.

Si en cambio necesitás correr el **servidor** en Windows 7, eso sí es complicado:
Windows 7 solo soporta hasta Python 3.8.10, y este proyecto pide `uvicorn 0.34` y
`pydantic 2.13`, que necesitan Python 3.9+. Habría que fijar versiones anteriores
y ajustar anotaciones del código. Avisame y armo esa variante.

## Pruebas (desarrollo)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows
.venv/bin/python -m pip install -r requirements-dev.txt       # Linux/Mac
.venv/bin/python -m pytest tests -v
```

---

## Notas de seguridad

Esta herramienta está pensada para una **red interna de confianza**. El login es
usuario + PIN (guardado con PBKDF2, nunca en texto plano), pero no incluye HTTPS
ni bloqueo por intentos fallidos. No la expongas directamente a internet.
