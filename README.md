# 📣 Agente de Marketing Automatizado

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Anthropic](https://img.shields.io/badge/Claude%20API-191919?style=for-the-badge&logo=anthropic&logoColor=white)
![Meta](https://img.shields.io/badge/Meta%20Graph%20API-0668E1?style=for-the-badge&logo=meta&logoColor=white)
![WhatsApp](https://img.shields.io/badge/WhatsApp%20API-25D366?style=for-the-badge&logo=whatsapp&logoColor=white)
![License](https://img.shields.io/badge/Licencia-MIT-green?style=for-the-badge)

> **Un agente de IA que genera contenido, publica en redes y atiende clientes por WhatsApp — todo automático.**

Agente de IA que genera posts, publica en Facebook/Instagram y responde clientes en WhatsApp automáticamente.

## Características

- **Chat con IA**: El dueño pide posts en lenguaje natural y el agente los genera y publica
- **Publicación automática**: Posts programados se publican solos a la hora exacta
- **Respuesta automática a clientes**: WhatsApp y Facebook Messenger respondidos por IA
- **Panel web**: Ver posts, historial y mensajes de clientes desde el navegador

---

## Instalación rápida

### 1. Instalar dependencias

```bash
cd marketing-agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tus credenciales
```

### 3. Iniciar el servidor

```bash
python main.py
```

Abre **http://localhost:8000** en tu navegador.

---

## Obtener credenciales

### Claude API (Anthropic)
1. Ve a https://console.anthropic.com
2. Crea una API Key
3. Pégala en `ANTHROPIC_API_KEY`

### Facebook + Instagram (Meta)
1. Ve a https://developers.facebook.com
2. Crea una app de tipo **Business**
3. Agrega el producto **Facebook Login** y **Instagram Graph API**
4. Genera un **token de página de larga duración**
5. Copia el **Page ID** de tu página de Facebook
6. Copia el **Instagram Account ID** vinculado

### WhatsApp Business API
1. En la misma app de Meta, agrega el producto **WhatsApp**
2. En el sandbox de WhatsApp, copia el **Phone Number ID**
3. El token de acceso es el mismo `META_ACCESS_TOKEN`

### Configurar el Webhook (para recibir mensajes)
1. Despliega la app en un servidor con HTTPS (o usa **ngrok** para desarrollo):
   ```bash
   ngrok http 8000
   ```
2. En Meta Developers → Webhooks, pon la URL: `https://TU-URL/webhook/meta`
3. El verify token es el valor de `META_WEBHOOK_VERIFY_TOKEN` en tu `.env`
4. Suscríbete a los campos: `messages`, `messaging_postbacks`

---

## Uso

### Pedir posts al agente
Escribe en el chat:
- *"Crea un post de promoción para el fin de semana"*
- *"Crea un post y publícalo ahora en Facebook"*
- *"Genera 5 ideas de posts para esta semana"*
- *"Crea un post y prográmalo para el viernes a las 10am"*

### Respuestas automáticas
Una vez configurado el webhook, el agente responde automáticamente a:
- Mensajes de WhatsApp de clientes
- Mensajes de Facebook Messenger

---

## Estructura del proyecto

```
marketing-agent/
├── main.py                      # Punto de entrada
├── requirements.txt
├── .env.example
├── backend/
│   ├── config.py                # Variables de entorno
│   ├── database.py              # SQLite async
│   ├── models.py                # Modelos de DB
│   ├── scheduler.py             # Publicación automática
│   ├── agents/
│   │   ├── content_agent.py     # Claude para generar posts
│   │   └── response_agent.py    # Claude para responder clientes
│   ├── integrations/
│   │   ├── facebook.py          # Meta Graph API (FB + IG)
│   │   └── whatsapp.py          # WhatsApp Business API
│   └── routers/
│       ├── chat.py              # WebSocket del chat
│       ├── posts.py             # CRUD de posts
│       └── webhook.py           # Webhook de Meta
└── frontend/
    ├── index.html               # Interfaz web
    ├── style.css
    └── chat.js
```

<!-- Agrega capturas en docs/screenshots/ -->

---

## Desarrollado por Francisco Javier Laguna

Full-stack developer · React · Vue · .NET · PHP

[GitHub](https://github.com/jlaguna553) · [LinkedIn](https://www.linkedin.com/in/francisco-javier-laguna-mondrag%C3%B3n-80a798154/) · [CV Online](https://cv-online.jlaguna553.workers.dev/v/xrdcnyej)


## Ahorro de costos (rama `mejora-costos-felix-software`)

La publicación en Facebook/Instagram con la Graph API **no tiene costo por llamada**; el gasto real viene del LLM y, en WhatsApp, de las conversaciones iniciadas por el negocio. Esta versión lo reduce así:

| Medida | Efecto |
|---|---|
| Capa de respuestas sin IA (`backend/agents/free_replies.py`): saludos, intención de agendar, coincidencia con la KB y caché | Las preguntas repetidas se contestan con **$0** de IA |
| Modelo económico por defecto (`ANTHROPIC_*_MODEL`, Haiku) y `MAX_REPLY_TOKENS=350` | Cada llamada restante cuesta mucho menos |
| Historial recortado (`MAX_HISTORY_MESSAGES=4`) | Menos tokens de entrada |
| Calendario precargado: `POST /api/posts/import` con `data/calendar_felix_software.json` | Un mes de posts **sin generar con IA** |
| `LLM_PROVIDER=ollama` | Opción de $0 en API si corres un modelo local |
| Imágenes locales (`media/`) subidas directo a Facebook | Sin necesidad de hosting de imágenes |

Además se agregó captura de **leads** (`GET /api/leads/`, `PATCH /api/leads/{id}`) cuando alguien pide agendar o cotizar, y la KB inicial de Felix Software (`KB_SEED_FILE=data/kb_felix_software.json`).

```bash
pip install -r requirements.txt && python -m pytest -q
curl -X POST localhost:8000/api/posts/import -H 'content-type: application/json' -d @data/calendar_felix_software.json
```

> Las horas de `scheduled_at` están en UTC (10:00 en Ciudad de México = 16:00 UTC).
> La base `marketing_agent.db` ya no se versiona: contiene conversaciones reales.


## CRM de Felix Software en local

```bash
git checkout crm-local-felix
./scripts/run_local.sh            # http://localhost:8000
```

El script crea el entorno, siembra la base de conocimiento de Felix Software y arranca en **modo local** (`MOCK_INTEGRATIONS=true`): no llama a Meta ni a WhatsApp y, sin `ANTHROPIC_API_KEY`, usa una IA simulada que deja las dudas desconocidas como tickets. Abre la pestaña **🧪 Simulador** para escribir como si fueras un cliente.

| Pieza | Qué hace |
|---|---|
| Bot de bienvenida | Saludo, enlace de agenda y respuestas desde la base de conocimiento (sin costo de IA) |
| **CRM · Leads** | Todo contacto queda registrado con estado (Nuevo → Contactado → Agendado → Cliente/Perdido), hilo completo, notas y respuesta manual por el mismo canal |
| Aviso al dueño | WhatsApp a `OWNER_WHATSAPP` cuando alguien pide agendar y cuando llega una duda que el bot no sabe |
| Seguimiento automático | Si alguien pidió agendar y sigue en "Nuevo" tras `FOLLOWUP_AFTER_HOURS`, el bot le recuerda el enlace (máx. `FOLLOWUP_MAX`, solo dentro de la ventana de 24 h). Si respondes tú o cambias el estado, se calla |
| Tickets | Dudas que el bot no sabe; tu respuesta se envía al cliente y se guarda en la KB |
| Posts programados | El calendario de `data/` se publica solo en su horario (en local, a la bandeja de salida) |

Endpoints útiles: `GET /api/leads/`, `GET /api/leads/stats`, `POST /api/leads/{id}/reply`, `POST /api/dev/simulate`, `GET /api/dev/outbox`, `POST /api/dev/run-followups`.

### Probar con Meta real (opcional)
1. Pon en `.env`: `MOCK_INTEGRATIONS=false`, `META_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `META_WEBHOOK_VERIFY_TOKEN`, **`META_APP_SECRET`** (valida la firma del webhook) y `ANTHROPIC_API_KEY`.
2. Expón el puerto con un túnel: `ngrok http 8000`.
3. En Meta for Developers configura el webhook con `https://<tu-túnel>/webhook/meta` y el mismo verify token; suscribe `messages` (WhatsApp) y `messages` de la página (Messenger).
4. Con `RESTRICT_REMOTE_ADMIN=true` (por defecto) el panel **no** es accesible por el túnel: desde fuera solo responde `/webhook/meta`.

> Producción: el panel y la API no tienen login. No los publiques en internet sin autenticación.


## Workers AI (cuota gratuita) y RAG

`LLM_PROVIDER=workers_ai` usa los modelos abiertos de Cloudflare por REST. La cuota gratuita es de **10,000 neuronas por día para toda la cuenta**, así que se comparte con tus Workers (por ejemplo `cv-online`). Si se agota (error 3036), el agente no se cae: avisa al cliente que lo atenderá una persona y deja un ticket.

Estimación para 10,000 neuronas (150 tokens de salida, tarifas publicadas por Cloudflare):

| Modelo | KB completa (1,500 tok) | Con RAG (600 tok) |
|---|---|---|
| Llama 3.3 70B fp8 fast | ~141 respuestas/día | ~214 |
| Llama 3.1 8B fp8 | ~407 | ~821 |
| Llama 3.2 3B | ~869 | ~1,361 |

Son cálculos con tokens supuestos; mide el consumo real en el panel de Workers AI y en `GET /api/usage` (respuestas gratis, llamadas al modelo y tokens estimados que se ahorró el RAG).

**RAG sin base vectorial dedicada:** `backend/rag.py` envía al modelo solo las `RAG_TOP_K` entradas más relevantes de la KB. Por defecto usa coincidencia de palabras ($0). Con `RAG_EMBEDDINGS=true` agrega búsqueda semántica con embeddings de Workers AI, guardados en la propia base SQLite y comparados por coseno; para cientos de entradas es instantáneo. Una base vectorial (Vectorize, pgvector) solo se justifica con miles de vectores o si el agente corre dentro de un Worker.
