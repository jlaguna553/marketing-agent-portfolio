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
