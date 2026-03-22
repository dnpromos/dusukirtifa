import asyncio
import hashlib
import hmac
import json
import logging
import time

import httpx

from bot.config import WIRO_API_KEY, WIRO_API_SECRET, WIRO_BASE_URL

logger = logging.getLogger(__name__)

IATA_REFERENCE = """Türkiye'deki önemli havalimanı kodları:
- İstanbul (Havalimanı): IST
- İstanbul (Sabiha Gökçen): SAW
- Ankara (Esenboğa): ESB
- İzmir (Adnan Menderes): ADB
- Antalya: AYT
- Dalaman: DLM
- Bodrum (Milas): BJV
- Trabzon: TZX
- Adana: ADA
- Gaziantep: GZT
- Diyarbakır: DIY
- Kayseri: ASR
- Samsun: SZF
- Konya: KYA
- Van: VAN
- Erzurum: ERZ
- Hatay: HTY
- Mardin: MQM"""

PARSE_SYSTEM = """Sen bir uçuş arama asistanısın. Kullanıcının mesajından uçuş bilgilerini çıkar.

Görevin:
1. Kalkış şehrini/havalimanını IATA koduna çevir
2. Varış şehrini/havalimanını IATA koduna çevir
3. Gidiş tarihini YYYY-MM-DD formatına çevir
4. Dönüş tarihini YYYY-MM-DD formatına çevir (varsa)

{iata_ref}

Bugünün tarihi: {today}

SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma:
{{"origin": "XXX", "destination": "XXX", "depart_date": "YYYY-MM-DD", "return_date": "YYYY-MM-DD veya null"}}

Eğer bilgi eksikse veya anlayamadıysan:
{{"error": "eksik bilgiyi açıkla"}}
"""

CHAT_SYSTEM = """Sen "Düşük İrtifa" adlı bir Telegram uçuş asistanı botusun. Türkçe konuşuyorsun.
Samimi, yardımsever ve bilgilendiricsin. SADECE seyahat, uçuş, tatil konularında yardım edersin.
Seyahat dışı konularda kibarca "Ben sadece seyahat ve uçuş konularında yardımcı olabilirim" de.

MESAJ FORMATLAMA:
- Markdown KULLANMA (**, *, #, -, ` gibi). Telegram HTML kullanıyor.
- Kalın metin için <b>metin</b> kullan.
- Liste için emoji numaralar kullan: 1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣
- Şehir önerirken her birini ayrı satırda yaz, kısa açıklama ekle.
Örnek format:
1️⃣ <b>Barselona</b> — Gaudi, plajlar ve tapas cenneti
2️⃣ <b>Roma</b> — Tarihi kalıntılar ve İtalyan mutfağı
3️⃣ <b>Prag</b> — Uygun fiyat, masalsı mimari

Bugünün tarihi: {today}

YANIT FORMATI: Yanıtını SADECE aşağıdaki JSON formatlarından BİRİ ile ver. Başka hiçbir şey yazma.

═══ SOHBET AKSİYONU (API ÇAĞRISI YOK) ═══

"chat" aksiyonu — Kendi bilginle seyahat tavsiyesi ver, soru sor, bilgi paylaş:
{{"action": "chat", "message": "mesaj"}}

Bu aksiyonu şu durumlarda kullan:
- Kullanıcı tavsiye istiyor ("Nereye gideyim?", "Avrupa'da nere önerirsin?")
- Genel seyahat bilgisi soruyor ("Vizesi var mı?", "Havaalanı nasıl?")
- Selamlıyor, teşekkür ediyor
- Eksik bilgi var ve soru sorman lazım

ÖNEMLİ: Tavsiye verirken KENDİ BİLGİNİ kullan. Örnek:
- "İstanbul'dan Avrupa'ya nereye gideyim?" → 4-5 Avrupa şehri öner (Roma, Barselona, Paris, Prag, Budapeşte vb.), kısa açıklama yap, sonunda "Hangisine bakmamı istersin? Fiyatlarını kontrol edebilirim!" de.
- "Nisan ayında nereye gitsem?" → Mevsime uygun destinasyonlar öner.
- Kullanıcı belirli bir bölge istiyorsa (Avrupa, Asya, vb.) SADECE o bölgeden öner.

═══ API AKSİYONLARI (fiyat/bilet gerektiğinde) ═══

Aşağıdaki aksiyonları SADECE kullanıcı fiyat, bilet, tarih bilgisi istediğinde kullan:

1. Uçuş ara (kalkış + varış + tarih gerekli, aktarmasız filtre opsiyonel):
{{"action": "search_flight", "message": "mesaj", "origin": "XXX", "destination": "XXX", "depart_date": "YYYY-MM-DD", "return_date": "YYYY-MM-DD veya null", "direct": true/false}}

2. En ucuz rotalar (fiyat bazlı keşif — kalkış gerekli):
{{"action": "show_popular", "message": "mesaj", "origin": "XXX"}}

3. Aktarmasız uçuşlar (kalkış + varış + ay gerekli):
{{"action": "show_direct", "message": "mesaj", "origin": "XXX", "destination": "XXX", "month": "YYYY-MM"}}

4. Fiyat trendleri (kalkış + varış + ay gerekli):
{{"action": "show_trends", "message": "mesaj", "origin": "XXX", "destination": "XXX", "month": "YYYY-MM"}}

5. Son bulunan en ucuz biletler (kalkış gerekli, varış opsiyonel):
{{"action": "show_latest", "message": "mesaj", "origin": "XXX", "destination": "XXX veya null"}}

6. Fiyat takvimi (kalkış + varış + ay gerekli, aktarmasız filtre opsiyonel):
{{"action": "show_calendar", "message": "mesaj", "origin": "XXX", "destination": "XXX", "month": "YYYY-MM", "direct": true/false}}

7. Takip listesini göster:
{{"action": "list_flights", "message": "mesaj"}}

8. Takipten çıkar (uçuş ID gerekli):
{{"action": "remove_flight", "message": "mesaj", "flight_id": 123}}

═══ AKIŞ KURALLARI ═══

TAVSİYE vs FİYAT AYRIMI (ÇOK ÖNEMLİ):
- "Nereye gideyim?", "Ne önerirsin?", "Avrupa'da güzel yer?" → "chat" ile kendi bilginle 4-5 destinasyon öner. API çağrısı YAPMA.
- "En ucuz neresi?", "Fiyatlara bak", "Bilet kaç para?" → İşte O ZAMAN API aksiyonu kullan.
- Kullanıcı senin önerdiğin bir şehri seçince → Tarih sor, sonra "search_flight" veya "show_calendar" kullan.

BÖLGE FİLTRESİ:
- Kullanıcı "Avrupa" diyorsa → SADECE Avrupa şehirleri öner (Roma, Barselona, Paris, Amsterdam, Prag, Budapeşte, Viyana, Lizbon, Berlin, Atina vb.)
- Kullanıcı "Asya" diyorsa → SADECE Asya şehirleri öner
- "show_popular" aksiyonu API'den dönen sonuçlar iç hat olabilir — kullanıcı yurt dışı istiyorsa "chat" ile kendi önerini ver

GENEL KURALLAR:
- Eksik bilgi varsa "chat" ile sor, varsayma.
- "Takiplerim", "Listemi göster" → "list_flights"
- "X numaralı uçuşu sil/kaldır" → "remove_flight"
- "Şu an en ucuz ne var?", "Son fiyatlar" → "show_latest"
- "Hangi gün ucuz?", "Takvimi göster" → "show_calendar"
- "Aktarmasız uçuşlar takvimi" → "show_calendar" ile "direct": true kullan.
- "Aktarmasız bilet bul", "Direkt uçuş istiyorum" → "search_flight" ile "direct": true kullan.
- Önceki aramada aktarmasız uçuş/takvim gösterilmişse ve kullanıcı o sonuçlarla ilgili detay, bilet veya arama istiyorsa → "direct": true MUTLAKA ekle. Sohbet geçmişinde "aktarmasız" veya "direct" geçen takvim sonucu varsa direct=true kullan.
- Kısa ve öz cevaplar ver. Gereksiz uzatma.
- Doğal Türkçe yaz, emoji kullanabilirsin.

TAKİP EDEN ARAMALAR VE BAĞLAM:
- Sohbet geçmişini DİKKATLE oku. Önceki aramalardaki kalkış, varış, tarih bilgilerini hatırla.
- "Dönüş bileti bul" veya "bir hafta sonra dönüş" → Önceki aramanın TERS rotasını (origin↔destination) ve yeni tarihi kullan.
  Örnek: Önceki arama IST→AYT 15 Haziran ise, "bir hafta sonra dönüş" = AYT→IST 22 Haziran.
- "Aynısını ama temmuzda" → Aynı rota, yeni ay.
- "Başka tarih" veya "2 gün sonrası" → Önceki rotayı koru, tarihi güncelle.
- Kullanıcı senin önerdiğin bir şehri seçip "fiyat bak" derse → Hemen ilgili API aksiyonunu çağır.
"""

MAX_HISTORY = 30
POLL_INTERVAL = 0.4
MAX_POLL_ATTEMPTS = 25
WEBHOOK_TIMEOUT = 12.0
TERMINAL_STATUSES = {"task_postprocess_end", "task_cancel"}


def _generate_signature() -> tuple[str, str]:
    nonce = str(int(time.time()))
    message = f"{WIRO_API_SECRET}{nonce}"
    signature = hmac.new(
        WIRO_API_KEY.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return nonce, signature


def _auth_headers() -> dict:
    nonce, signature = _generate_signature()
    return {
        "x-api-key": WIRO_API_KEY,
        "x-nonce": nonce,
        "x-signature": signature,
    }


async def _submit_task(client: httpx.AsyncClient, prompt: str,
                       system_instructions: str,
                       callback_url: str = "") -> str | None:
    form_data = {
        "prompt": prompt,
        "systemInstructions": system_instructions,
        "thinkingLevel": "medium",
        "maxOutputTokens": 2048,
    }
    if callback_url:
        form_data["callbackUrl"] = callback_url

    resp = await client.post(
        f"{WIRO_BASE_URL}/Run/google/gemini-3-flash",
        headers=_auth_headers(),
        data=form_data,
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error(f"Wiro submit failed: {resp.status_code} {resp.text}")
        return None

    data = resp.json()
    if not data.get("result"):
        logger.error(f"Wiro submit error: {data.get('errors')}")
        return None

    return data.get("taskid")


async def _extract_text_from_task(task_data: dict,
                                  client: httpx.AsyncClient | None = None) -> str | None:
    if isinstance(task_data, dict):
        tasks = task_data.get("tasklist", [])
        if tasks:
            task = tasks[0]
        else:
            task = task_data
    else:
        return None

    status = task.get("status", "")
    if status == "task_cancel":
        return None

    outputs = task.get("outputs", [])
    for output in outputs:
        url = output.get("url", "")
        if url:
            dl_client = client or httpx.AsyncClient()
            try:
                text_resp = await dl_client.get(url, timeout=15)
                if text_resp.status_code == 200:
                    return text_resp.text
            finally:
                if not client:
                    await dl_client.aclose()

    debug = task.get("debugoutput", "")
    if debug:
        return debug
    return None


async def _wait_webhook(callback_url: str, future: asyncio.Future,
                        client: httpx.AsyncClient) -> str | None:
    try:
        task_data = await asyncio.wait_for(future, timeout=WEBHOOK_TIMEOUT)
        return await _extract_text_from_task(task_data, client)
    except asyncio.TimeoutError:
        logger.warning("Wiro webhook timed out, falling back to poll")
        return None
    except asyncio.CancelledError:
        return None


async def _poll_task(client: httpx.AsyncClient, task_id: str) -> str | None:
    for _ in range(MAX_POLL_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL)

        resp = await client.post(
            f"{WIRO_BASE_URL}/Task/Detail",
            headers=_auth_headers(),
            data={"taskid": task_id},
            timeout=15,
        )
        if resp.status_code != 200:
            continue

        data = resp.json()
        tasks = data.get("tasklist", [])
        if not tasks:
            continue

        task = tasks[0]
        status = task.get("status", "")

        if status in TERMINAL_STATUSES:
            return await _extract_text_from_task(data, client)

    logger.warning(f"Wiro task {task_id} timed out after polling")
    return None


async def _run_ai(prompt: str, system_instructions: str) -> str | None:
    from bot.config import WEBHOOK_BASE_URL

    use_webhook = bool(WEBHOOK_BASE_URL)
    callback_url = ""
    future = None
    callback_id = ""

    if use_webhook:
        from bot.services.webhook import get_callback_url, cleanup_future
        callback_url, future = get_callback_url()
        callback_id = callback_url.rsplit("/", 1)[-1]

    async with httpx.AsyncClient() as client:
        task_id = await _submit_task(
            client, prompt, system_instructions,
            callback_url=callback_url,
        )
        if not task_id:
            if callback_id:
                cleanup_future(callback_id)
            return None

        if use_webhook and future:
            result = await _wait_webhook(callback_url, future, client)
            if result is not None:
                return result
            logger.info(f"Webhook miss for {task_id}, polling...")

        return await _poll_task(client, task_id)


def _parse_json_response(text: str) -> dict | None:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        clean = clean.rsplit("```", 1)[0]
    try:
        return json.loads(clean.strip())
    except (json.JSONDecodeError, IndexError):
        return None


async def parse_flight_request(user_message: str) -> dict:
    from datetime import date
    today = date.today().isoformat()
    system = PARSE_SYSTEM.format(today=today, iata_ref=IATA_REFERENCE)

    result_text = await _run_ai(user_message, system)
    if not result_text:
        return {"error": "AI yanıt veremedi. Lütfen tekrar deneyin."}

    parsed = _parse_json_response(result_text)
    if parsed:
        return parsed

    logger.warning(f"Failed to parse Gemini response: {result_text}")
    return {"error": "Yanıt anlaşılamadı. Lütfen daha açık yazın."}


def _build_history_prompt(history: list[dict], new_message: str) -> str:
    parts = []
    for entry in history[-MAX_HISTORY:]:
        role = "Kullanıcı" if entry["role"] == "user" else "Asistan"
        parts.append(f"{role}: {entry['text']}")
    parts.append(f"Kullanıcı: {new_message}")
    return "\n".join(parts)


async def chat(user_message: str, history: list[dict]) -> dict:
    from datetime import date
    today = date.today().isoformat()
    system = CHAT_SYSTEM.format(today=today)

    prompt = _build_history_prompt(history, user_message)

    result_text = await _run_ai(prompt, system)
    if not result_text:
        return {
            "action": "chat",
            "message": "Yanıt alamadım, tekrar dener misin? 🤔",
        }

    parsed = _parse_json_response(result_text)
    if parsed and "action" in parsed:
        return parsed

    return {"action": "chat", "message": result_text.strip()}
