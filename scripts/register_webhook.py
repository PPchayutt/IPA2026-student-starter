"""Register or update the Webex messages/created webhook to point to the active HTTPS tunnel URL."""

from pathlib import Path
import sys
import requests

REPO_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_DIR / ".env"
WEBEX_API = "https://webexapis.com/v1"


def load_dotenv(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main():
    if len(sys.argv) < 2:
        print("วิธีใช้: python scripts/register_webhook.py https://<ชื่อลิงก์>.trycloudflare.com")
        sys.exit(1)

    base_url = sys.argv[1].strip().rstrip("/")
    if base_url.endswith("/webhook"):
        base_url = base_url[: -len("/webhook")]

    health_url = f"{base_url}/health"
    target_url = f"{base_url}/webhook"

    # 1. อ่าน WEBEX_BOT_TOKEN จากไฟล์ .env
    if not ENV_PATH.exists():
        print(f"[ERROR] ไม่พบไฟล์ .env ที่ {ENV_PATH}")
        sys.exit(1)

    env = load_dotenv(ENV_PATH)
    token = env.get("WEBEX_BOT_TOKEN", "")
    if not token:
        print("[ERROR] ไม่พบค่า WEBEX_BOT_TOKEN ในไฟล์ .env")
        sys.exit(1)

    # 2. เช็กว่าลิงก์ Tunnel ยิงทะลุไปถึง Docker /health ได้จริง
    try:
        r_health = requests.get(health_url, timeout=10)
        print(f"[HEALTH] GET {health_url} -> HTTP {r_health.status_code}: {r_health.text.strip()}")
        if r_health.status_code != 200:
            print("[ERROR] /health ไม่ตอบ HTTP 200 กรุณาเช็กว่าเปิด Docker (docker compose up -d webhook) อยู่หรือไม่")
            sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] ติดต่อ {health_url} ไม่สำเร็จ: {exc}")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}

    # 3. ดึงรายการ Webhook เดิมของบอทมาดู
    r_hooks = requests.get(f"{WEBEX_API}/webhooks", headers=headers, timeout=10)
    r_hooks.raise_for_status()
    existing = r_hooks.json().get("items", [])

    kept_hook = None
    for hook in existing:
        if (
            hook.get("resource") == "messages"
            and hook.get("event") == "created"
            and not hook.get("filter")
            and kept_hook is None
        ):
            kept_hook = hook
        else:
            requests.delete(f"{WEBEX_API}/webhooks/{hook['id']}", headers=headers, timeout=10)

    # 4. ถ้ามีอยู่แล้วสั่ง PUT อัปเดต targetUrl ใหม่ ถ้ายังไม่มีสั่ง POST สร้างใหม่
    if kept_hook is not None:
        r_upd = requests.put(
            f"{WEBEX_API}/webhooks/{kept_hook['id']}",
            headers=headers,
            json={
                "name": "ipa2026-webhook",
                "targetUrl": target_url,
                "status": "active",
            },
            timeout=10,
        )
        r_upd.raise_for_status()
        hook_info = r_upd.json()
        print(f"[WEBHOOK] อัปเดตลิงก์ใหม่สำเร็จ! -> {hook_info.get('targetUrl')} (status={hook_info.get('status')})")
    else:
        r_new = requests.post(
            f"{WEBEX_API}/webhooks",
            headers=headers,
            json={
                "name": "ipa2026-webhook",
                "targetUrl": target_url,
                "resource": "messages",
                "event": "created",
            },
            timeout=10,
        )
        r_new.raise_for_status()
        hook_info = r_new.json()
        print(f"[WEBHOOK] สร้าง Webhook สำเร็จ! -> {hook_info.get('targetUrl')} (status={hook_info.get('status')})")


if __name__ == "__main__":
    main()
