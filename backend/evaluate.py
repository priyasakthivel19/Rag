"""
Evaluate the chatbot on a test set   ->   python evaluate.py [eval/questions.json]

  "doc"     : answer lives in your PDFs. expected_source / expected_keyword (optional)
  "general" : NOT in your PDFs. PDFs must NOT be used. expected_keyword (optional)
Add "skip": true to ignore an entry (used by the placeholder examples).
"""

import csv
import json
import sys
import time

from src.engine import RAGEngine

PAUSE_SECONDS = 2  # be gentle with Groq free-tier rate limits


def pct(ok: int, total: int) -> str:
    return f"{ok}/{total} ({100 * ok / total:.0f}%)" if total else "n/a"


def main(path: str = "eval/questions.json") -> None:
    engine = RAGEngine()
    if not engine.has_index:
        raise SystemExit("No index found. Run `python ingest.py` first.")

    with open(path, encoding="utf-8") as f:
        items = [i for i in json.load(f) if not i.get("skip")]
    if not items:
        raise SystemExit("No active questions. Edit eval/questions.json (remove \"skip\": true).")

    rows, latencies = [], []
    hit = hit_total = route = kw = kw_total = 0

    for n, it in enumerate(items, 1):
        q, typ = it["question"], it.get("type", "doc")
        try:
            out = engine.ask(q)
        except Exception as e:
            print(f"[{n}/{len(items)}] ERROR: {e}")
            rows.append({"type": typ, "question": q, "error": str(e)})
            continue

        retrieved_files = {r["source"] for r in out["retrieved"]}
        retrieval_ok = routing_ok = keyword_ok = ""

        if typ == "doc":
            routing_ok = out["used_docs"]
            if it.get("expected_source"):
                retrieval_ok = it["expected_source"] in retrieved_files
                hit_total += 1
                hit += retrieval_ok
        else:
            routing_ok = not out["used_docs"]
        route += bool(routing_ok)

        if it.get("expected_keyword"):
            keyword_ok = it["expected_keyword"].lower() in out["answer"].lower()
            kw_total += 1
            kw += keyword_ok

        latencies.append(out["latency"])
        print(f"[{n}/{len(items)}] {typ:7} retrieval={retrieval_ok!s:5} routing={routing_ok!s:5} "
              f"keyword={keyword_ok!s:5} {out['latency']}s | {q[:50]}")
        rows.append({
            "type": typ, "question": q, "retrieval_ok": retrieval_ok, "routing_ok": routing_ok,
            "keyword_ok": keyword_ok, "used_docs": out["used_docs"], "latency_s": out["latency"],
            "top_sources": "; ".join(f"{r['source']} p.{r['page']} ({r['score']})" for r in out["retrieved"]),
            "answer": out["answer"],
        })
        time.sleep(PAUSE_SECONDS)

    print("\n=========== SUMMARY ===========")
    print("Retrieval hit-rate (right file in top-K) :", pct(hit, hit_total))
    print("Routing accuracy (PDF vs general)        :", pct(route, len(latencies)))
    print("Keyword found in answer                  :", pct(kw, kw_total))
    if latencies:
        print(f"Latency avg / max                        : {sum(latencies)/len(latencies):.2f}s / {max(latencies):.2f}s")

    fields = ["type", "question", "retrieval_ok", "routing_ok", "keyword_ok", "used_docs",
              "latency_s", "top_sources", "answer", "error"]
    with open("eval_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("Saved: eval_results.csv")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/questions.json")
