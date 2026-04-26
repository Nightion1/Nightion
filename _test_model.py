import urllib.request, json

payload = json.dumps({
    "model": "gemma4",
    "prompt": "hi",
    "stream": False,
}).encode()

req = urllib.request.Request(
    "http://localhost:11434/api/generate",
    data=payload,
    headers={"Content-Type": "application/json"},
)

try:
    resp = urllib.request.urlopen(req, timeout=60)
    print("OK:", resp.read().decode()[:300])
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    if hasattr(e, "read"):
        print("Body:", e.read().decode()[:500])
