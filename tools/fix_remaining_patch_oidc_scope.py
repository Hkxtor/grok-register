#!/usr/bin/env python3
from pathlib import Path

script = Path(__file__).resolve().with_name("apply_remaining_hardening.py")
text = script.read_text(encoding="utf-8")
old = '''oauth = replace_once(oauth, "                status = int(getattr(response, \\\"status\\\", 200) or 200)\\n", "                status = int(getattr(response, \\\"status\\\", 200) or 200)\\n            _check_cancel(cancel)\\n", "post postcheck")'''
new = '''post_start = oauth.find("def _post_form")
post_end = oauth.find("def request_device_code", post_start)
if post_start < 0 or post_end < 0:
    raise RuntimeError("post postcheck: _post_form boundaries not found")
post_block = oauth[post_start:post_end]
post_block = replace_once(
    post_block,
    "                status = int(getattr(response, \\\"status\\\", 200) or 200)\\n",
    "                status = int(getattr(response, \\\"status\\\", 200) or 200)\\n            _check_cancel(cancel)\\n",
    "post postcheck",
)
oauth = oauth[:post_start] + post_block + oauth[post_end:]'''
count = text.count(old)
if count != 1:
    raise RuntimeError(f"OIDC postcheck patch anchor expected once, got {count}")
script.write_text(text.replace(old, new, 1), encoding="utf-8")
print("OIDC postcheck migration edit scoped to _post_form")
