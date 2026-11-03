"""
Estudio de posts: texto con el Worker `felix-post-studio` + plantilla de imagen con Pillow.

Las imágenes NO se analizan: solo se validan, se re-codifican y se pegan en la plantilla.
"""
import io
import logging
import re
import uuid
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

MEDIA_STUDIO = Path("media/studio")
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGES = 4
SIZE = 1080
NAVY, BLUE, AMBER, INK = (11, 27, 58), (47, 107, 255), (255, 176, 32), (247, 248, 252)
ID_RE = re.compile(r"^[a-f0-9]{16}$")


class StudioError(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


def valid_id(post_id: str) -> bool:
    return bool(ID_RE.match(post_id or ""))


# ── Texto (Worker) ───────────────────────────────────────────

def _simulated(campaign: str, network: str, cta: str) -> dict:
    first = campaign.strip().split("\n")[0][:90]
    cta = cta or "Agenda tu asesoría gratuita"
    return {
        "facebook": f"✨ {first}\n\nSoftware a tu medida con renta mensual accesible.\n📅 {cta}",
        "instagram": f"✨ {first}\n\n📅 {cta}",
        "headline": " ".join(first.split()[:7]),
        "cta": cta,
        "hashtags": ["#FelixSoftware", "#CaaS", "#software", "#pymes", "#mexico"],
    }


async def generate_copy(campaign: str, network: str, tone: str, cta: str, facts: list[str]) -> dict:
    """Devuelve {'post': {...}, 'warnings': [...], 'source': 'worker'|'simulated'}."""
    if not settings.studio_worker_url:
        if settings.mock_integrations:
            return {"post": _simulated(campaign, network, cta), "warnings": [], "source": "simulated"}
        raise StudioError("Falta STUDIO_WORKER_URL (despliega worker/studio y ponlo en .env)", "not_configured")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                settings.studio_worker_url.rstrip("/") + "/generate",
                headers={"Authorization": f"Bearer {settings.studio_worker_key}"},
                json={"campaign": campaign, "network": network, "tone": tone, "cta": cta, "facts": facts},
            )
    except httpx.HTTPError as e:
        raise StudioError(f"No se pudo contactar al Worker: {e.__class__.__name__}", "unreachable")
    if r.status_code == 429:
        code = (r.json() or {}).get("error", "rate_limited") if r.headers.get("content-type", "").startswith("application/json") else "rate_limited"
        msg = "Se agotó la cuota gratuita diaria de Workers AI; reinicia a las 00:00 UTC." if code == "daily_limit" else "Demasiadas solicitudes; espera un minuto."
        raise StudioError(msg, code)
    if r.status_code == 401:
        raise StudioError("STUDIO_WORKER_KEY no coincide con el secreto STUDIO_KEY del Worker", "unauthorized")
    if r.status_code != 200:
        raise StudioError(f"El Worker respondió {r.status_code}", "worker_error")
    data = r.json()
    return {"post": data["post"], "warnings": data.get("warnings", []), "source": "worker"}


# ── Imágenes ─────────────────────────────────────────────────

def sanitize_image(raw: bytes) -> Image.Image:
    """Valida y re-codifica: descarta metadatos y cualquier contenido que no sea una imagen real."""
    if len(raw) > MAX_IMAGE_BYTES:
        raise StudioError("Cada imagen debe pesar máximo 8 MB", "image_too_large")
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
        img = Image.open(io.BytesIO(raw))
        if img.width * img.height > MAX_IMAGE_PIXELS:
            raise StudioError("La imagen es demasiado grande en píxeles", "image_too_large")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except StudioError:
        raise
    except Exception:
        raise StudioError("Uno de los archivos no es una imagen válida", "bad_image")
    img.thumbnail((2400, 2400))
    return img


def save_source(img: Image.Image, post_id: str, index: int = 0) -> Path:
    (MEDIA_STUDIO / "src").mkdir(parents=True, exist_ok=True)
    path = MEDIA_STUDIO / "src" / (f"{post_id}.png" if index == 0 else f"{post_id}_{index}.png")
    img.save(path, "PNG")
    return path


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / f"Inter-{weight}.otf"), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def compose_template(src: Path | None, headline: str, cta: str, out: Path) -> Path:
    """Cuadrado 1080×1080: foto (o fondo de marca), degradado, logo, titular y barra de CTA."""
    if src and src.is_file():
        base = ImageOps.fit(Image.open(src).convert("RGB"), (SIZE, SIZE), Image.LANCZOS)
    else:
        base = Image.new("RGB", (SIZE, SIZE), NAVY)
    canvas = base.convert("RGBA")

    grad = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    top = int(SIZE * 0.35)
    for y in range(top, SIZE):
        a = int(235 * ((y - top) / (SIZE - top)) ** 1.4)
        gd.line([(0, y), (SIZE, y)], fill=(*NAVY, a))
    canvas = Image.alpha_composite(canvas, grad)
    d = ImageDraw.Draw(canvas)

    # logo
    d.rounded_rectangle((48, 48, 48 + 64, 48 + 64), radius=16, fill=BLUE)
    f_logo = _font("ExtraBold", 40)
    d.text((48 + 32, 48 + 32), "F", font=f_logo, fill=INK, anchor="mm")
    d.text((128, 80), "Felix Software", font=_font("SemiBold", 30), fill=INK, anchor="lm")

    # CTA (barra inferior)
    cta = (cta or "Agenda tu asesoría gratuita").strip()
    f_cta = _font("SemiBold", 34)
    while d.textlength(cta, font=f_cta) > SIZE - 96 - 80 and f_cta.size > 22:
        f_cta = _font("SemiBold", f_cta.size - 2)
    bar_h = 92
    bar_y = SIZE - 48 - bar_h
    d.rounded_rectangle((48, bar_y, SIZE - 48, bar_y + bar_h), radius=26, fill=AMBER)
    d.text((SIZE // 2, bar_y + bar_h // 2), cta, font=f_cta, fill=NAVY, anchor="mm")

    # titular: baja el tamaño hasta que quepa en máx. 4 líneas
    headline = (headline or "Software a tu medida").strip()
    max_w, size, lines = SIZE - 96, 92, []
    while size >= 40:
        font = _font("ExtraBold", size)
        lines = _wrap(d, headline, font, max_w)
        if len(lines) <= 4:
            break
        size -= 6
    line_h = int(size * 1.12)
    y = bar_y - 36 - line_h * len(lines)
    for ln in lines:
        d.text((48, y), ln, font=font, fill=INK)
        y += line_h

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out


def source_path(post_id: str) -> Path | None:
    if not valid_id(post_id):
        return None
    p = MEDIA_STUDIO / "src" / f"{post_id}.png"
    return p if p.is_file() else None


def composed_path(post_id: str) -> Path:
    return MEDIA_STUDIO / f"{post_id}.png"
