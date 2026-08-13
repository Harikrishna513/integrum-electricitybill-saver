import json
path = r"C:\Users\Admin\.cursor\projects\c-Users-Admin-Downloads-bescom-bill-saver-ai\agent-transcripts\cba35c97-1fea-4ad8-8b48-fd9343e1325f\cba35c97-1fea-4ad8-8b48-fd9343e1325f.jsonl"
out = open("tmp_m19b.txt", "w", encoding="utf-8")
with open(path, encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if i != 5:
            continue
        text = json.loads(line)["message"]["content"][0]["text"]
        idx = text.find("contextual question rewriting")
        out.write(text[idx:idx+2500] if idx>=0 else "nf")
out.close()
print("ok")
