import { useRef, useState } from "react";

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  streaming?: boolean;
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const historyRef = useRef<{ role: string; content: string }[]>([]);

  async function send() {
    const question = input.trim();
    if (!question || sending) return;
    setInput("");
    setSending(true);

    const nextMessages: Message[] = [...messages, { role: "user", content: question }, { role: "assistant", content: "", streaming: true }];
    setMessages(nextMessages);
    const assistantIndex = nextMessages.length - 1;

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, history: historyRef.current }),
      });
      if (!resp.body) throw new Error("no response body");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalText = "";
      let citations: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          const line = event.trim();
          if (!line.startsWith("data: ")) continue;
          const payload = JSON.parse(line.slice(6));
          if (payload.type === "token") {
            finalText += payload.content;
            setMessages((prev) => {
              const copy = [...prev];
              copy[assistantIndex] = { role: "assistant", content: finalText, streaming: true };
              return copy;
            });
          } else if (payload.type === "done") {
            citations = payload.citations ?? [];
          }
        }
      }

      setMessages((prev) => {
        const copy = [...prev];
        copy[assistantIndex] = { role: "assistant", content: finalText, citations, streaming: false };
        return copy;
      });
      historyRef.current = [
        ...historyRef.current,
        { role: "user", content: question },
        { role: "assistant", content: finalText },
      ].slice(-10);
    } catch {
      setMessages((prev) => {
        const copy = [...prev];
        copy[assistantIndex] = { role: "assistant", content: "Sorry, something went wrong reaching the chatbot.", streaming: false };
        return copy;
      });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="card chat-card">
      <h2 className="chart-title">Chat</h2>
      <p className="chart-subtitle">Ask about papers, authors or collaborations - every answer cites real dblp records.</p>

      <div className="chat-messages">
        {messages.length === 0 && <p className="chart-empty">Try: "How many papers did VLDB publish in 2020?"</p>}
        {messages.map((m, i) => (
          <div key={i} className={`chat-bubble chat-bubble-${m.role} ${m.streaming ? "chat-bubble-streaming" : ""}`}>
            <p>{m.content || (m.streaming ? "..." : "")}</p>
            {m.citations && m.citations.length > 0 && (
              <div className="chat-citations">
                {m.citations.map((key) => (
                  <a key={key} className="chat-citation-chip" href={`https://dblp.org/rec/${key}`} target="_blank" rel="noreferrer">
                    {key}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask a question..."
          disabled={sending}
        />
        <button onClick={send} disabled={sending || !input.trim()}>Send</button>
      </div>
    </div>
  );
}
