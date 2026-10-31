/* Progressive enhancement: the same form remains usable without JavaScript. */
(() => {
  "use strict";
  const root = document.querySelector("[data-farmer-chat]");
  if (!root) return;
  const form = root.querySelector("[data-chat-form]");
  const input = form?.querySelector('textarea[name="message"]');
  const transcript = root.querySelector("[data-chat-transcript]");
  const scroll = root.querySelector("[data-chat-scroll]");
  if (!form || !input || !transcript || !scroll || !window.fetch || !window.FormData) return;
  const send = form.querySelector("[data-chat-send]");
  const error = root.querySelector("[data-chat-error]");
  const loading = root.querySelector("[data-chat-loading]");
  const clearForm = root.querySelector("[data-chat-clear]");
  const count = root.querySelector("[data-chat-count]");
  const history = root.querySelector("[data-chat-history]");
  const number = new Intl.NumberFormat(document.documentElement.lang === "bn" ? "bn-BD" : "en", { useGrouping: false });
  let busy = false;

  const icon = (name) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#icon-${name}`);
    svg.appendChild(use);
    return svg;
  };
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };
  const safeLink = (value, sameOrigin = false) => {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const url = new URL(value, location.origin);
      if (sameOrigin) return url.origin === location.origin ? url : null;
      return url.protocol === "https:" && !url.username && !url.password ? url : null;
    } catch (_) {
      return null;
    }
  };
  const bottom = (force = false) => {
    if (force || scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 160) {
      scroll.scrollTo({ top: scroll.scrollHeight, behavior: "auto" });
    }
  };
  const updateCount = () => {
    const length = input.value.length;
    if (count) {
      count.textContent = `${number.format(length)} / ${number.format(2000)}`;
      count.classList.toggle("is-over", length > 2000);
    }
  };
  const showError = (message) => {
    error.textContent = message || root.dataset.errorLabel;
    error.hidden = false;
    input.setAttribute("aria-invalid", "true");
    error.focus({ preventScroll: true });
  };
  const setBusy = (value) => {
    busy = value;
    send.disabled = value;
    input.readOnly = value;
    root.querySelector(".chat-main").setAttribute("aria-busy", value ? "true" : "false");
    loading.hidden = !value;
    const label = send.querySelector("span");
    if (label) label.textContent = value ? root.dataset.sendingLabel : root.dataset.sendLabel;
    form.querySelectorAll("select, input[type='checkbox']").forEach((field) => { field.disabled = value; });
    if (clearForm) clearForm.querySelector("button").disabled = value;
  };
  const appendMessage = (message) => {
    const isUser = message.role === "user";
    const article = node("article", `chat-message chat-message-${isUser ? "user" : "assistant"}`);
    const avatar = node("span", "chat-avatar");
    avatar.setAttribute("aria-hidden", "true");
    if (isUser) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", "12"); circle.setAttribute("cy", "8"); circle.setAttribute("r", "3.5");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", "M5 21v-2a7 7 0 0 1 14 0v2");
      svg.append(circle, path); avatar.appendChild(svg);
    } else avatar.appendChild(icon("leaf"));
    const content = node("div", "chat-message-content");
    const meta = node("div", "chat-message-meta");
    meta.appendChild(node("strong", "", isUser ? root.dataset.userLabel : root.dataset.assistantLabel));
    if (!isUser) meta.appendChild(node("span", "chat-message-mode", message.mode === "local" ? root.dataset.localLabel : message.mode === "ai" ? root.dataset.aiLabel : root.dataset.knowledgeLabel));
    const bubble = node("div", "chat-bubble", message.body);
    bubble.style.whiteSpace = "pre-wrap";
    content.append(meta, bubble);
    if (message.notice) content.appendChild(node("p", "chat-message-notice", message.notice));
    if (Array.isArray(message.sources)) {
      const sources = node("div", "chat-sources");
      sources.appendChild(node("span", "", root.dataset.sourceLabel));
      message.sources.slice(0, 6).forEach((source) => {
        if (!source || typeof source !== "object") return;
        const url = safeLink(source.url);
        if (!url || !source.title) return;
        const link = node("a", "", source.title);
        link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
        link.appendChild(icon("arrow")); sources.appendChild(link);
      });
      if (sources.childElementCount > 1) content.appendChild(sources);
    }
    article.append(avatar, content); transcript.appendChild(article);
  };
  const rememberConversation = (payload, question) => {
    const url = safeLink(payload.conversation_url, true);
    const clearUrl = safeLink(payload.clear_url, true);
    const conversationInput = form.querySelector('[name="conversation"]');
    if (conversationInput) conversationInput.value = String(payload.conversation_id);
    if (url) window.history.replaceState(null, "", url.pathname + url.search);
    if (clearForm && clearUrl) { clearForm.action = clearUrl.href; clearForm.hidden = false; }
    if (!history || !url) return;
    history.querySelectorAll("[data-conversation-id]").forEach((entry) => {
      entry.classList.remove("is-active"); entry.removeAttribute("aria-current");
    });
    const id = String(payload.conversation_id);
    let entry = Array.from(history.querySelectorAll("[data-conversation-id]")).find((item) => item.dataset.conversationId === id);
    if (!entry) {
      entry = node("a", "chat-history-item");
      entry.href = url.href; entry.dataset.conversationId = id;
      entry.append(icon("leaf"), node("span", "", question.slice(0, 70)), icon("arrow"));
      entry.lastElementChild.classList.add("chat-history-arrow");
      history.prepend(entry);
      root.querySelector("[data-chat-history-empty]")?.remove();
      const entries = history.querySelectorAll("[data-conversation-id]");
      Array.from(entries).slice(12).forEach((item) => item.remove());
    }
    entry.classList.add("is-active"); entry.setAttribute("aria-current", "page");
  };

  root.querySelectorAll("[data-chat-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      if (busy) return;
      input.value = button.textContent.trim();
      updateCount(); input.focus();
      input.scrollIntoView({ block: "nearest", behavior: "auto" });
    });
  });
  input.addEventListener("input", () => {
    updateCount(); input.removeAttribute("aria-invalid"); error.hidden = true;
  });
  clearForm?.addEventListener("submit", (event) => {
    if (busy || !window.confirm(root.dataset.confirmClear)) event.preventDefault();
  });
  // A collapsed history keeps the conversation within reach on smaller screens.
  const disclosure = root.querySelector(".chat-history-disclosure");
  if (disclosure && window.matchMedia("(max-width: 900px)").matches) disclosure.open = false;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy) return;
    const question = input.value.trim();
    if (!question) { showError(root.dataset.emptyLabel); input.focus(); return; }
    if (input.value.length > 2000) { showError(root.dataset.lengthLabel); input.focus(); return; }
    const data = new FormData(form);
    error.hidden = true; input.removeAttribute("aria-invalid");
    setBusy(true); bottom(true);
    try {
      const response = await fetch(form.action, {
        method: "POST", body: data, credentials: "same-origin",
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      });
      const type = response.headers.get("content-type") || "";
      if (!type.includes("application/json")) throw new Error(root.dataset.errorLabel);
      const payload = await response.json();
      if (!response.ok) {
        let detail = payload.error;
        if (payload.errors && typeof payload.errors === "object") {
          const fieldErrors = Object.values(payload.errors).flat()
            .map((value) => typeof value === "string" ? value : value?.message)
            .filter((value) => typeof value === "string");
          if (fieldErrors.length) detail = fieldErrors.join(" ");
        }
        throw new Error(typeof detail === "string" && detail ? detail : root.dataset.errorLabel);
      }
      if (!payload.user || !payload.assistant || typeof payload.user.body !== "string" || typeof payload.assistant.body !== "string") throw new Error(root.dataset.errorLabel);
      const wasNearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 160;
      root.querySelector("[data-chat-welcome]")?.setAttribute("hidden", "");
      appendMessage(payload.user); appendMessage(payload.assistant);
      rememberConversation(payload, question);
      input.value = ""; updateCount();
      form.querySelectorAll(".errorlist, .chat-server-error").forEach((item) => item.remove());
      if (wasNearBottom) bottom(true);
    } catch (failure) {
      showError(failure instanceof Error ? failure.message : root.dataset.errorLabel);
    } finally {
      setBusy(false);
      input.focus({ preventScroll: true });
    }
  });
  updateCount();
  if (transcript.children.length) bottom(true);
})();
