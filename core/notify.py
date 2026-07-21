"""Discord webhook notifications (Phase 5). Fire-and-forget on a background
thread so a slow or failing request never blocks the executor."""

import json
import os
import threading

import requests

TIMEOUT_S = 15


def _post(url: str, payload: dict, image_path: str | None, log, ok_message: str | None = None):
    try:
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                files = {"file": (os.path.basename(image_path), f, "image/png")}
                r = requests.post(url, data={"payload_json": json.dumps(payload)},
                                   files=files, timeout=TIMEOUT_S)
        else:
            r = requests.post(url, json=payload, timeout=TIMEOUT_S)
        if r.status_code >= 300:
            log(f"Discord webhook failed: {r.status_code} {r.text[:200]}")
        elif ok_message:
            log(ok_message)
    except Exception as e:
        log(f"Discord webhook error: {e}")


def send_result(webhook_url: str, stage: str, won: bool, loop_no: int,
                 duration_s: float, screenshot_path: str | None = None,
                 loss_streak: int = 0, ping_streak_at: int = 3,
                 log=lambda m: None):
    if not webhook_url:
        return

    embed = {
        "title": f"{stage} - {'WIN' if won else 'LOSS'}",
        "color": 0x2ECC71 if won else 0xE74C3C,
        "fields": [
            {"name": "Loop", "value": str(loop_no), "inline": True},
            {"name": "Duration", "value": f"{duration_s:.0f}s", "inline": True},
        ],
    }

    image_path = None
    if screenshot_path and os.path.exists(screenshot_path):
        embed["image"] = {"url": f"attachment://{os.path.basename(screenshot_path)}"}
        image_path = screenshot_path

    content = ""
    if not won and loss_streak >= ping_streak_at:
        content = f"@here {loss_streak} losses in a row on **{stage}**"

    payload = {"content": content, "embeds": [embed]}
    threading.Thread(target=_post, args=(webhook_url, payload, image_path, log),
                      daemon=True).start()


def send_test(webhook_url: str, log=lambda m: None):
    if not webhook_url:
        log("No webhook URL set.")
        return
    payload = {"content": "TD Macro - webhook test. If you see this, it works."}
    threading.Thread(
        target=_post, args=(webhook_url, payload, None, log),
        kwargs={"ok_message": "Webhook test sent successfully."},
        daemon=True,
    ).start()
