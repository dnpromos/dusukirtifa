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
Samimi, yardımsever ve bilgilendiricsin. Kullanıcıyla doğal bir sohbet yürütüyorsun.
Kullanıcı seninle yazarak her şeyi yapabilir — menüye gerek yok.

Görevlerin:
- Uçuş aramak ve en uygun bileti bulmak
- Tatil ve seyahat önerileri vermek
- Popüler rotaları ve fiyat trendlerini göstermek
- Uçuşları takibe almak ve takip listesini yönetmek
- Havalimanları ve şehirler hakkında bilgi vermek

{iata_ref}

Bugünün tarihi: {today}

ÖNEMLI: Yanıtını SADECE aşağıdaki JSON formatlarından BİRİ ile ver. Başka hiçbir şey yazma.

Aksiyonlar ve formatları:

1. Sohbet (soru sor, bilgi ver, selamla):
{{"action": "chat", "message": "mesaj"}}

2. Uçuş ara (kalkış + varış + tarih gerekli):
{{"action": "search_flight", "message": "mesaj", "origin": "XXX", "destination": "XXX", "depart_date": "YYYY-MM-DD", "return_date": "YYYY-MM-DD veya null"}}

3. Popüler rotalar (sadece kalkış şehri gerekli):
{{"action": "show_popular", "message": "mesaj", "origin": "XXX"}}

4. Aktarmasız uçuşlar (kalkış + varış + ay gerekli):
{{"action": "show_direct", "message": "mesaj", "origin": "XXX", "destination": "XXX", "month": "YYYY-MM"}}

5. Fiyat trendleri (kalkış + varış + ay gerekli):
{{"action": "show_trends", "message": "mesaj", "origin": "XXX", "destination": "XXX", "month": "YYYY-MM"}}

6. Takip listesini göster:
{{"action": "list_flights", "message": "mesaj"}}

7. Takipten çıkar (uçuş ID gerekli):
{{"action": "remove_flight", "message": "mesaj", "flight_id": 123}}

Kurallar:
- Eksik bilgi varsa "chat" aksiyonu ile SORU SOR. Tahmin etme, varsayma.
- "Tatile çıkmak istiyorum", "Nereye gideyim?" → Kalkış şehrini sor, sonra "show_popular" kullan.
- "Haziranda tatil istiyorum" → Kalkış şehrini sor. Şehri öğrenince "show_popular" kullan.
- Kullanıcı kalkış şehrini verince hemen aksiyona geç, tekrar sorma.
- "Takiplerim", "Listemi göster" → "list_flights" kullan.
- "X numaralı uçuşu sil/kaldır" → "remove_flight" kullan.
- Kısa ve öz cevaplar ver. Gereksiz uzatma.
- Doğal Türkçe yaz, emoji kullanabilirsin.
- Sohbet geçmişine bak ve bağlamı koru. Önceki mesajlardaki bilgileri kullan.
"""

MAX_HISTORY = 10
POLL_INTERVAL = 0.4
MAX_POLL_ATTEMPTS = 25
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
                       temperature: str = "0.1") -> str | None:
    resp = await client.post(
        f"{WIRO_BASE_URL}/Run/google/gemini-3-flash",
        headers=_auth_headers(),
        data={
            "prompt": prompt,
            "systemInstructions": system_instructions,
            "thinkingLevel": "low",
            "temperature": temperature,
            "topP": "0.95",
            "maxOutputTokens": 1024,
        },
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
            if status == "task_cancel":
                return None
            outputs = task.get("outputs", [])
            for output in outputs:
                url = output.get("url", "")
                if url:
                    text_resp = await client.get(url, timeout=15)
                    if text_resp.status_code == 200:
                        return text_resp.text

            debug = task.get("debugoutput", "")
            if debug:
                return debug
            return None

    logger.warning(f"Wiro task {task_id} timed out after polling")
    return None


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

    async with httpx.AsyncClient() as client:
        task_id = await _submit_task(client, user_message, system)
        if not task_id:
            return {"error": "AI servisine bağlanılamadı. Lütfen tekrar deneyin."}

        result_text = await _poll_task(client, task_id)
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
    system = CHAT_SYSTEM.format(today=today, iata_ref=IATA_REFERENCE)

    prompt = _build_history_prompt(history, user_message)

    async with httpx.AsyncClient() as client:
        task_id = await _submit_task(client, prompt, system, temperature="0.5")
        if not task_id:
            return {
                "action": "chat",
                "message": "Şu an bağlantı sorunu yaşıyorum. Biraz sonra tekrar dener misin? 🙏",
            }

        result_text = await _poll_task(client, task_id)
        if not result_text:
            return {
                "action": "chat",
                "message": "Yanıt alamadım, tekrar dener misin? 🤔",
            }

    parsed = _parse_json_response(result_text)
    if parsed and "action" in parsed:
        return parsed

    return {"action": "chat", "message": result_text.strip()}
