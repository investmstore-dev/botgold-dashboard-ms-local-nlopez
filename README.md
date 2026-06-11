# BOT Mining Store GOLD — Dashboard

Dashboard web local para monitorear cuentas FTMO, controlar el bot de trading y visualizar el progreso en tiempo real. Diseño **cyberpunk / dark** con tecnología Flask + HTML vanilla.

---

## Vista general

- **Monitoreo en tiempo real** de balance, equity, P&L diario y total
- **Progreso FTMO** con barra visual hacia el objetivo de ganancia
- **Medidores de riesgo**: pérdida diaria y drawdown vs. límites FTMO
- **Curva de equity** (sparkline) por cuenta
- **Control del bot**: iniciar y detener sin usar terminal
- **Gestión de cuentas**: agregar, editar y eliminar cuentas desde la UI
- **Historial de operaciones**: últimas 15 trades cerradas y posiciones abiertas
- Auto-refresh cada 30 segundos

---

## Requisitos

- Python 3.10+
- Flask

```bash
pip install flask
```

---

## Instalación

```bash
git clone https://github.com/investmstore-dev/botgold-dashboard-ms-local-nlopez.git
cd botgold-dashboard-ms-local-nlopez
pip install flask
```

---

## Levantar el dashboard

```bash
python dashboard_server.py
```

Luego abre en el navegador:
```
http://localhost:5050
```

El servidor corre en el puerto **5050** por defecto.

---

## Estructura de archivos

```
dashboard/
├── dashboard_server.py   # Servidor Flask — API + control de procesos bot
├── dashboard.html        # Frontend (HTML + CSS + JS vanilla)
├── accounts.json         # Configuración de cuentas (generado por la UI)
└── README.md
```

---

## Cómo agregar una cuenta FTMO

1. Abre el dashboard en `http://localhost:5050`
2. Haz click en **+ NUEVA CUENTA** (esquina superior derecha de la sección de cuentas)
3. Completa el formulario:

| Campo | Descripción | Ejemplo |
|---|---|---|
| **Nombre** | Nombre descriptivo | `FTMO $10k — Eval #1` |
| **Balance inicial** | Capital en USD | `10000` |
| **Fase** | 1=Challenge, 2=Verification, 3=Fondeada | `1` |
| **Objetivo ganancia %** | Meta de ganancia FTMO | `10` (fase 1) / `5` (fase 2) |
| **Pérdida diaria max %** | Límite de pérdida diaria | `5` |
| **Drawdown máximo %** | Límite de drawdown total | `10` |
| **Ruta SQLite** | Base de datos del bot | `gold_bot.db` |
| **Status file** | JSON generado por el EA en MT5 | `C:/Users/.../goldbot_status.json` |

4. Haz click en **GUARDAR CUENTA**

La cuenta aparecerá inmediatamente en el dashboard.

---

## Cómo encontrar la ruta del Status File (MT5)

El EA del bot escribe un archivo JSON con el estado en tiempo real de la cuenta. La ruta estándar es:

```
C:\Users\TU_USUARIO\AppData\Roaming\MetaQuotes\Terminal\XXXXXXXXXXXXXXXX\MQL5\Files\goldbot_status.json
```

También puedes encontrarla en MT5:
**Archivo → Abrir carpeta de datos → MQL5/Files**

---

## Control del bot desde el dashboard

Cada card de cuenta tiene dos controles:

| Botón | Acción |
|---|---|
| **INICIAR BOT** (verde) | Lanza `main.py` para esa cuenta en un proceso separado |
| **DETENER BOT** (rojo) | Termina el proceso del bot para esa cuenta |

El estado se actualiza automáticamente en el próximo refresh (30 segundos) o al recargar la página.

---

## API REST del servidor

El dashboard expone una API local que puedes usar para integraciones:

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/data` | Estado completo de todas las cuentas |
| `GET` | `/api/accounts` | Lista de cuentas en accounts.json |
| `POST` | `/api/accounts` | Crear nueva cuenta |
| `PUT` | `/api/accounts/<id>` | Editar cuenta existente |
| `DELETE` | `/api/accounts/<id>` | Eliminar cuenta |
| `POST` | `/api/accounts/<id>/start` | Iniciar bot para esa cuenta |
| `POST` | `/api/accounts/<id>/stop` | Detener bot para esa cuenta |

### Ejemplo — obtener estado de cuentas

```bash
curl http://localhost:5050/api/data
```

Respuesta:
```json
{
  "accounts": [...],
  "burned_total": 0,
  "server_time": "2026-06-11T...",
  "next_run": "2026-06-11T13:05:00+00:00"
}
```

---

## Formato del archivo accounts.json

El archivo se gestiona automáticamente desde la UI, pero si necesitas editarlo manualmente:

```json
[
  {
    "id": "ftmo_10k_01",
    "name": "FTMO $10k — Eval #1",
    "initial_balance": 10000.0,
    "target_pct": 10.0,
    "daily_loss_limit_pct": 5.0,
    "max_dd_pct": 10.0,
    "phase": 1,
    "db_path": "gold_bot.db",
    "status_file": "C:/Users/.../goldbot_status.json"
  }
]
```

---

## Colores del dashboard

| Color | Significado |
|---|---|
| 🟡 Dorado | Cuenta activa en Fase 1 |
| 🟢 Verde | Objetivo alcanzado / ganancia |
| 🟣 Púrpura | Indicadores de drawdown / estrategia |
| 🔴 Rojo | Cuenta eliminada / pérdida / alerta |
| 🔵 Cyan | Posiciones abiertas |

---

## Solución de problemas

**El dashboard no carga:**
```bash
# Verificar que el puerto 5050 no está en uso
netstat -ano | findstr :5050
# Si hay proceso, mátalo:
taskkill /PID <PID> /F
```

**La cuenta muestra $0 en todo:**
- Verificar que el EA está activo en MT5
- Verificar la ruta del `status_file` en la configuración de la cuenta
- El archivo debe existir y tener formato JSON válido

**El bot no inicia desde el dashboard:**
- Verificar que `main.py` existe en el mismo directorio que `dashboard_server.py`
- Verificar que todas las dependencias del bot están instaladas

---

## Licencia

Uso privado — Mining Store © 2026
