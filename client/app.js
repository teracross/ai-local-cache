const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("send");
const answerEl = document.getElementById("answer");
const badgeEl = document.getElementById("badge");

async function send() {
  const prompt = promptEl.value.trim();
  if (!prompt) return;

  sendBtn.disabled = true;
  badgeEl.innerHTML = "";
  answerEl.textContent = "Thinking...";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    answerEl.textContent = data.answer; // textContent avoids HTML injection
    const badge = document.createElement("span");
    badge.className = `badge ${data.source}`;
    badge.textContent = `source: ${data.source}`;
    badgeEl.appendChild(badge);
  } catch (err) {
    answerEl.textContent = `Request failed: ${err.message}`;
    const badge = document.createElement("span");
    badge.className = "badge error";
    badge.textContent = "error";
    badgeEl.appendChild(badge);
  } finally {
    sendBtn.disabled = false;
  }
}

sendBtn.addEventListener("click", send);
promptEl.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
