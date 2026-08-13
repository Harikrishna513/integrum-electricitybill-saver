import json,re
path = r"C:\Users\Admin\.cursor\projects\c-Users-Admin-Downloads-bescom-bill-saver-ai\agent-transcripts\cba35c97-1fea-4ad8-8b48-fd9343e1325f\cba35c97-1fea-4ad8-8b48-fd9343e1325f.jsonl"
out = open("tmp_m19.txt", "w", encoding="utf-8")
with open(path, encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if i not in (5, 6):
            continue
        for part in json.loads(line).get("message", {}).get("content", []):
            if part.get("type") != "text":
                continue
            text = part["text"]
            for pat in [r"Milestone 19", r"contextual", r"rewrit", r"memory", r"question rewriting", r"# 31", r"# 33"]:
                for m in re.finditer(pat, text, re.I):
                    pos = m.start()
                    out.write(f"\n===== L{i} {m.group()} @{pos} =====\n")
                    out.write(text[pos:pos+2200])
                    out.write("\n")
out.close()
print("size", __import__("os").path.getsize("tmp_m19.txt"))
