"""Terminal chatbot   ->   python chat_cli.py"""

from src.engine import RAGEngine

if __name__ == "__main__":
    engine = RAGEngine()
    if not engine.has_index:
        print("(No index yet - run `python ingest.py` for PDF answers. General questions still work.)")
    print("Chatbot ready. Type 'exit' to quit.\n")

    history = []
    while True:
        q = input("You: ").strip()
        if q.lower() in {"exit", "quit"}:
            break
        if not q:
            continue
        out = engine.ask(q, history)
        print(f"\nBot: {out['answer']}")
        if out["sources"]:
            print("Sources:", ", ".join(f"{s['source']} p.{s['page']}" for s in out["sources"]))
        else:
            print("(answered from general knowledge)")
        print(f"[{out['latency']}s]\n")
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": out["answer"]}]
