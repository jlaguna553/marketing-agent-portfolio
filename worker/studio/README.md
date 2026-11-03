# felix-post-studio

Worker de Cloudflare que **redacta** el texto de un post (Facebook + Instagram) a partir de la información de una campaña.
Usa Workers AI (cuota gratuita diaria, ~16 neuronas por post con el 8B, estimado ≈ 600 posts/día). **Las imágenes nunca llegan aquí.**

## Desplegar (una sola vez, desde tu computadora)

```bash
cd worker/studio
npx wrangler login                 # abre el navegador y autorizas tu cuenta
openssl rand -hex 24               # genera una clave; cópiala
npx wrangler secret put STUDIO_KEY # pega esa clave cuando la pida
npx wrangler deploy                # imprime la URL, p. ej. https://felix-post-studio.<tu-subdominio>.workers.dev
```

Luego, en el `.env` del agente:

```
STUDIO_WORKER_URL=https://felix-post-studio.<tu-subdominio>.workers.dev
STUDIO_WORKER_KEY=<la misma clave>
```

Reinicia el agente y abre la pestaña **✨ Estudio de posts**.

## Seguridad
- Sin `STUDIO_KEY` el Worker responde 503 (cerrado por defecto). Comparación de clave en tiempo constante.
- Límite nativo de 20 solicitudes/min (`[[ratelimits]]`) y cuerpo máx. 20 KB.
- El texto de la campaña va delimitado y el prompt lo trata como datos, no como instrucciones.
- Si el modelo escribe un precio que no está en la campaña ni en los datos de tu KB, la respuesta trae `warnings`.
- Cuota agotada (error 3036) → 429 `daily_limit`; el panel te lo explica.

## Pruebas
`npm test` (Node 20+, sin dependencias; el modelo se simula).
