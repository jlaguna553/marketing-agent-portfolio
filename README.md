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
