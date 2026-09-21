// K9Chat — MessageList / MessageBubble component
// Renders the chat transcript for the active session and persists messages
// to localStorage (k9chat_msgs_<session_id>). No backend calls here — the
// network requests live in ChatInput; this module only owns rendering +
// local persistence.

const MessageList = (() => {
  const chatHistoryEl = document.getElementById("chat-history");

  // Topic-organized starter prompts -- shown as a picker card on every
  // empty/new chat instead of one flat random pool, so a visitor can
  // browse by what they're actually curious about rather than hoping a
  // relevant question shows up by chance. Every topic here is in-scope
  // regardless of Framework Mode (all pure K9-AIF/K9X content), so this
  // shows the same way in both states.
  const TOPIC_PROMPTS = {
    "ABB": [
      "What does ABB stand for, and how is it different from an SBB?",
      "What is a Squad, and why doesn't it know about its Orchestrator?",
      "Explain the Router → Orchestrator → Squad → Agent hierarchy.",
      "What does K9ModelRouter actually do?",
    ],
    "SBB": [
      "Show me a minimal BaseAgent subclass.",
      "When should I use K9ValidationLoopAgent instead of BaseAgent?",
      "What's the difference between K9PlanningLoopAgent and K9ValidationLoopAgent?",
      "How does a generated agent actually invoke an LLM?",
    ],
    "Ecosystem": [
      "What is k9x_Shield and what does it actually check?",
      "What's the difference between k9x_Shield and Zero Trust?",
      "What is K9X HIL, and when would I need it?",
      "What does k9x_satan actually test?",
    ],
    "Patterns": [
      "What does 'Not just agents. Architecture.' actually mean?",
      "What's the difference between K9-AIF and a framework like LangChain?",
      "What is K9-AIF's stance on TOGAF and OOD?",
      "What's the Critic-Actor pattern, and when should I use it instead of a validation loop?",
    ],
    "Best Practices": [
      "How does K9-AIF handle governance for an agent?",
      "Why must agents call llm_invoke() instead of the router directly?",
      "What's the three-layer decoupling rule, and why does it matter?",
      "When is it actually safe to use NoopGovernance?",
    ],
    "How to start": [
      "How do I run an example app locally, like this one (k9chat)?",
      "What's the fastest way to scaffold a new K9-AIF agent?",
      "What do I need installed before I can build with K9-AIF?",
    ],
    "Developer Studio": [
      "What is K9X Studio, and how do I generate a project from it?",
      "How do I run K9X Studio locally?",
      "Does K9X Studio replace the CLI generator, or complement it?",
    ],
  };
  const TOPICS = Object.keys(TOPIC_PROMPTS);

  function pickFromTopic(topic, n = 4) {
    const pool = [...(TOPIC_PROMPTS[topic] || [])];
    const picked = [];
    while (picked.length < n && pool.length > 0) {
      const i = Math.floor(Math.random() * pool.length);
      picked.push(pool.splice(i, 1)[0]);
    }
    return picked;
  }

  function renderStarterPrompts() {
    const card = document.createElement("div");
    card.className = "topic-picker-card";

    const title = document.createElement("div");
    title.className = "topic-picker-title";
    title.textContent = "Explore a topic";
    card.appendChild(title);

    const topicRow = document.createElement("div");
    topicRow.className = "topic-picker-row";
    card.appendChild(topicRow);

    const chipRow = document.createElement("div");
    chipRow.className = "starter-prompts";
    card.appendChild(chipRow);

    function renderChipsFor(topic) {
      chipRow.innerHTML = "";
      pickFromTopic(topic).forEach(q => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "starter-chip";
        chip.textContent = q;
        chip.addEventListener("click", () => {
          const input = document.getElementById("message-input");
          input.value = q;
          card.remove();
          ChatInput.send();
        });
        chipRow.appendChild(chip);
      });
    }

    TOPICS.forEach((topic, i) => {
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "topic-pill";
      pill.textContent = topic;
      pill.addEventListener("click", () => {
        topicRow.querySelectorAll(".topic-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        renderChipsFor(topic);
      });
      topicRow.appendChild(pill);
      if (i === 0) {
        pill.classList.add("active");
        renderChipsFor(topic);
      }
    });

    chatHistoryEl.appendChild(card);
  }

  function loadMessages(sessionId) {
    return JSON.parse(localStorage.getItem("k9chat_msgs_" + sessionId) || "[]");
  }

  function saveMessages(sessionId, msgs) {
    localStorage.setItem("k9chat_msgs_" + sessionId, JSON.stringify(msgs));
  }

  function formatElapsed(ms) {
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
  }

  function formatTime(ts) {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function scrollToBottom() {
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
  }

  function copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
      const original = btn.textContent;
      btn.textContent = "✓";
      setTimeout(() => { btn.textContent = original; }, 1200);
    }).catch(() => {});
  }

  // Edit-and-resubmit: drops everything from `index` onward, on both
  // sides -- the visible/local transcript AND the server's own memory of
  // the conversation (ChatAgent.truncate_history()), or the model would
  // still answer as if the erased turns actually happened. Refills the
  // input with the original text rather than auto-resending, so it can
  // actually be edited, not just replayed.
  async function editMessage(index, text) {
    const sessionId = SessionSidebar.activeId;
    saveMessages(sessionId, loadMessages(sessionId).slice(0, index));
    try {
      await fetch(`/chat/session/${sessionId}/truncate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keep_count: index }),
      });
    } catch (err) {
      // Local history is already truncated regardless; a failed server
      // call here just means the model might still recall the erased
      // turns for its next reply -- not ideal, not worth blocking on.
    }
    renderHistory(sessionId);
    const input = document.getElementById("message-input");
    input.value = text;
    input.focus();
  }

  // MessageBubble — builds one message DOM node (user or assistant).
  // `index` is this message's position in the session's stored array --
  // only meaningful for the edit button, so callers appending a message
  // (rather than replaying stored history) that never gets edited don't
  // strictly need to pass it, but appendMessage always does.
  function addBubble(role, text, meta = {}, index = null) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role}`;

    const col = document.createElement("div");
    col.className = "msg-col";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    col.appendChild(bubble);

    const metaRow = document.createElement("div");
    metaRow.className = "msg-meta";

    const timeSpan = document.createElement("span");
    timeSpan.className = "msg-time";
    if (meta.ts) timeSpan.textContent = formatTime(meta.ts);
    metaRow.appendChild(timeSpan);

    if (role === "user" && index != null) {
      const editBtn = document.createElement("button");
      editBtn.className = "msg-edit";
      editBtn.title = "Edit and resubmit";
      editBtn.textContent = "✎";
      editBtn.addEventListener("click", () => editMessage(index, text));
      metaRow.appendChild(editBtn);
    }

    let elapsedSpan = null;
    if (role === "assistant") {
      elapsedSpan = document.createElement("span");
      elapsedSpan.className = "msg-elapsed";
      if (meta.elapsed_ms != null) elapsedSpan.textContent = formatElapsed(meta.elapsed_ms);
      metaRow.appendChild(elapsedSpan);

      const copyBtn = document.createElement("button");
      copyBtn.className = "msg-copy";
      copyBtn.title = "Copy response";
      copyBtn.textContent = "⧉";
      copyBtn.addEventListener("click", () => copyToClipboard(bubble.textContent, copyBtn));
      metaRow.appendChild(copyBtn);

      if (meta.evaluation) {
        const ev = meta.evaluation;
        const gradeEl = document.createElement("span");
        gradeEl.className = `msg-grade grade-${ev.grade.toLowerCase()}`;
        gradeEl.title = `${ev.verdict} · Score: ${ev.score} · ${ev.rationale}`;
        gradeEl.textContent = `${ev.grade} ${ev.score}`;
        metaRow.appendChild(gradeEl);
      }

      if (meta.faq_match) {
        const fm = meta.faq_match;
        const faqEl = document.createElement("span");
        faqEl.className = "msg-faq-match";
        faqEl.title = `Deterministic answer from ${fm.source} -- no LLM call (retrieve-then-rerank match, score ${fm.score})`;
        faqEl.textContent = "FAQ match";
        metaRow.appendChild(faqEl);
      }
    }

    col.appendChild(metaRow);
    wrapper.appendChild(col);
    chatHistoryEl.appendChild(wrapper);
    scrollToBottom();

    return { wrapper, bubble, timeSpan, elapsedSpan };
  }

  function addThinkingBubble() {
    const wrapper = document.createElement("div");
    wrapper.className = "message assistant";
    const col = document.createElement("div");
    col.className = "msg-col";
    const bubble = document.createElement("div");
    bubble.className = "bubble thinking";
    bubble.innerHTML = `<span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
    col.appendChild(bubble);
    wrapper.appendChild(col);
    chatHistoryEl.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
  }

  function removeNode(node) {
    if (node && node.parentNode) node.parentNode.removeChild(node);
  }

  function persistMessage(sessionId, role, text, meta = {}) {
    const messages = loadMessages(sessionId);
    const entry = { role, content: text, ts: meta.ts || Date.now() };
    if (meta.elapsed_ms != null) entry.elapsed_ms = meta.elapsed_ms;
    messages.push(entry);
    saveMessages(sessionId, messages);
    return messages;
  }

  function appendMessage(sessionId, role, text, meta = {}) {
    const ts = meta.ts || Date.now();
    const messages = persistMessage(sessionId, role, text, { ...meta, ts });
    addBubble(role, text, { ...meta, ts }, messages.length - 1);
    return messages;
  }

  function renderHistory(sessionId) {
    const messages = loadMessages(sessionId);
    chatHistoryEl.innerHTML = "";
    if (messages.length === 0) {
      addBubble("assistant", "Hello. K9Chat is ready.", {});
      renderStarterPrompts();
      return;
    }
    messages.forEach((m, i) => addBubble(m.role, m.content, m, i));
  }

  function clear(sessionId) {
    saveMessages(sessionId, []);
    chatHistoryEl.innerHTML = "";
  }

  function addEvalBadge(bubbleRef, evaluation) {
    if (!evaluation || !bubbleRef) return;
    const metaRow = bubbleRef.wrapper.querySelector(".msg-meta");
    if (!metaRow) return;
    if (metaRow.querySelector(".msg-grade")) return; // already added
    const ev = evaluation;
    const gradeEl = document.createElement("span");
    gradeEl.className = `msg-grade grade-${ev.grade.toLowerCase()}`;
    gradeEl.title = `${ev.verdict} · Score: ${ev.score} · ${ev.rationale}`;
    gradeEl.textContent = `${ev.grade} ${ev.score}`;
    metaRow.appendChild(gradeEl);
  }

  function addFaqMatchBadge(bubbleRef, faqMatch) {
    if (!faqMatch || !bubbleRef) return;
    const metaRow = bubbleRef.wrapper.querySelector(".msg-meta");
    if (!metaRow) return;
    if (metaRow.querySelector(".msg-faq-match")) return; // already added
    const el = document.createElement("span");
    el.className = "msg-faq-match";
    el.title = `Deterministic answer from ${faqMatch.source} -- no LLM call (retrieve-then-rerank match, score ${faqMatch.score})`;
    el.textContent = "FAQ match";
    metaRow.appendChild(el);
  }

  let learnToastTimer = null;
  function showLearnToast(correctedFact) {
    if (!correctedFact) return;
    let el = document.getElementById("learn-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "learn-toast";
      el.className = "learn-toast";
      document.body.appendChild(el);
    }
    el.innerHTML = `<strong>Learned:</strong> ${correctedFact}`;
    // Reflow before adding .show so the transition actually plays even if
    // a toast is already visible (retriggering the same class wouldn't).
    el.classList.remove("show");
    void el.offsetWidth;
    el.classList.add("show");
    clearTimeout(learnToastTimer);
    learnToastTimer = setTimeout(() => el.classList.remove("show"), 5000);
  }

  return {
    loadMessages,
    saveMessages,
    renderHistory,
    addBubble,
    addThinkingBubble,
    addEvalBadge,
    addFaqMatchBadge,
    showLearnToast,
    removeNode,
    appendMessage,
    persistMessage,
    scrollToBottom,
    clear,
  };
})();
