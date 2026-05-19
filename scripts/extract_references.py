import json, re, os, sys
from collections import Counter
from datetime import datetime

# Accept paths from command line or env, with sensible defaults
CAPTURE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "CAPTURE_FILE",
    os.path.join(os.path.expanduser("~"), "Desktop", "doubao_capture.txt")
)
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
    "OUTPUT_DIR",
    os.path.join(os.path.expanduser("~"), "Desktop")
)

with open(CAPTURE, "r", encoding="utf-8") as f:
    content = f.read()

msg_refs = {}
msg_queries = {}
msg_answers = {}
msg_mode = {}
msg_conv = {}
msg_question = {}

for line in content.split("\n"):
    s = line.strip()
    if not s.startswith("data: {"):
        continue
    try:
        obj = json.loads(s[6:])
    except:
        continue

    cmd = obj.get("cmd")

    if cmd == 50200:
        try:
            n = obj["downlink_body"]["bot_reply_loading_update_notify"]
            ext = n["ext"]
            mid = ext.get("message_id", "")
            cid = n.get("conversation_id", "")
            if not mid:
                continue
            msg_conv[mid] = cid
            msg_mode[mid] = "browsing" if "browsing" in ext.get("agent_intention", "") else msg_mode.get(mid, "chat")

            rs = ext.get("search_references", "")
            if rs and len(rs) > 5:
                try:
                    refs = json.loads(rs)
                except:
                    continue
                if mid not in msg_refs:
                    msg_refs[mid] = []
                for r in refs:
                    tc = r["text_card"]
                    msg_refs[mid].append({
                        "title": tc.get("title", ""),
                        "url": tc.get("url", ""),
                        "sitename": tc.get("sitename", ""),
                        "summary": tc.get("summary", "")[:500]
                    })

            qs = ext.get("search_queries", "")
            if qs and mid not in msg_queries:
                try:
                    msg_queries[mid] = json.loads(qs)
                except:
                    pass
        except:
            continue

    elif cmd == 300:
        try:
            body = obj["downlink_body"].get("fetch_chunk_message_downlink_body", {})
            mid = body.get("message_id", "")
            if not mid:
                continue
            inner = json.loads(body.get("content", "{}"))
            text = inner.get("text", "").replace("\\n", "\n").replace("\\t", "\t")
            msg_answers[mid] = msg_answers.get(mid, "") + text

            mq = body.get("ext", {}).get("mult_query", "")
            if mq and mid not in msg_question:
                msg_question[mid] = mq
                if mid not in msg_queries:
                    msg_queries[mid] = [mq]
        except:
            continue

# Deduplicate refs
for mid in msg_refs:
    seen = set()
    uniq = []
    for r in msg_refs[mid]:
        if r["url"] not in seen:
            seen.add(r["url"])
            uniq.append(r)
    msg_refs[mid] = uniq

# Group QAs by conversation
conv_qas = {}
brand_kw = ["苹果", "Apple", "iPhone", "MacBook", "iPad", "大疆", "DJI",
            "华为", "Huawei", "小米", "Xiaomi", "三星", "Samsung",
            "抖音", "字节", "Google", "微软", "Microsoft", "极飞",
            "京东", "淘宝", "Intel", "M5", "M4", "M1"]

for mid in sorted(msg_refs.keys(), key=int):
    cid = msg_conv.get(mid, "unknown")
    refs = msg_refs.get(mid, [])
    queries = msg_queries.get(mid, [])
    answer = msg_answers.get(mid, "")
    question = msg_question.get(mid, "")

    if not question and queries:
        question = queries[0]
    if not queries and question:
        queries = [question]

    sc = dict(Counter(r["sitename"] for r in refs))
    brands = []
    for r in refs:
        t = r["title"] + r["summary"]
        for bk in brand_kw:
            if bk.lower() in t.lower() and bk not in brands:
                brands.append(bk)

    qa = {
        "task_id": mid,
        "question": question,
        "mode": msg_mode.get(mid, "chat"),
        "search_keywords": queries,
        "search_sources": refs,
        "search_summary": f"搜索 {len(queries)} 个关键词，参考 {len(refs)} 篇资料",
        "thinking_process": "",
        "answer": answer,
        "total_references": len(refs),
        "statistics": {
            "sitename_counts": sc,
            "brands": brands,
            "token_usage": {"total_input_tokens": 0, "total_output_tokens": 0, "total_tokens": 0}
        }
    }
    if cid not in conv_qas:
        conv_qas[cid] = []
    conv_qas[cid].append(qa)

if not conv_qas:
    print("ERROR: No conversations found!")
    exit(1)

# Write/update files
for cid, qas in conv_qas.items():
    existing = None
    for f in os.listdir(OUTPUT):
        if f.startswith("doubao_conv_") and f.endswith(".json"):
            fp = os.path.join(OUTPUT, f)
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    ex = json.load(fh)
                if ex.get("data", {}).get("conversation_id") == cid:
                    existing = fp
                    break
            except:
                pass

    data = {
        "code": 0,
        "msg": "success",
        "data": {
            "conversation_id": cid,
            "updated_at": datetime.now().isoformat(),
            "conversations": qas
        }
    }

    if existing:
        with open(existing, "r", encoding="utf-8") as fh:
            old = json.load(fh)
        old_ids = {q["task_id"] for q in old["data"]["conversations"]}
        added = 0
        for q in qas:
            if q["task_id"] not in old_ids:
                old["data"]["conversations"].append(q)
                old_ids.add(q["task_id"])
                added += 1
        old["data"]["conversations"].sort(key=lambda x: x["task_id"])
        old["data"]["updated_at"] = datetime.now().isoformat()
        data = old
        print(f"[{cid}] +{added} new QA(s)")
    else:
        print(f"[{cid}] NEW, {len(qas)} QA(s)")

    out_path = os.path.join(OUTPUT, f"doubao_conv_{cid}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"  -> {out_path}")
    for q in qas:
        print(f"     [{q['task_id']}] {q['question'][:50]} | {q['total_references']} refs | {len(q['answer'])} chars")

print(f"\nDone. {len(conv_qas)} file(s).")
