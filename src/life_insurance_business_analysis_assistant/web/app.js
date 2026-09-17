import { consumeEventStream } from "./sse.mjs";

const elements = {
  serviceState: document.querySelector("#service-state"),
  templateSelect: document.querySelector("#template-select"),
  templatePath: document.querySelector("#template-path"),
  sectionCount: document.querySelector("#section-count"),
  stepCount: document.querySelector("#step-count"),
  conversationTitle: document.querySelector("#conversation-title"),
  conversationState: document.querySelector("#conversation-state"),
  chatContext: document.querySelector("#chat-context"),
  welcome: document.querySelector("#welcome"),
  conversation: document.querySelector("#conversation"),
  userMessageText: document.querySelector("#user-message-text"),
  assistantIntro: document.querySelector("#assistant-intro"),
  processDetails: document.querySelector("#process-details"),
  pipelineTitle: document.querySelector("#pipeline-title"),
  progressCount: document.querySelector("#progress-count"),
  timeline: document.querySelector("#timeline"),
  formMessage: document.querySelector("#form-message"),
  reportContent: document.querySelector("#report-content"),
  reportActions: document.querySelector("#report-actions"),
  copyButton: document.querySelector("#copy-button"),
  downloadButton: document.querySelector("#download-button"),
  suggestionButton: document.querySelector("#suggestion-button"),
  newChatButton: document.querySelector("#new-chat-button"),
  composer: document.querySelector("#composer"),
  promptInput: document.querySelector("#prompt-input"),
  sendButton: document.querySelector("#send-button"),
  chatScroll: document.querySelector("#chat-scroll"),
};

const state = {
  templates: [],
  report: null,
  running: false,
  controller: null,
};

function selectedTemplate() {
  return state.templates[Number(elements.templateSelect.value)] || null;
}

function setServiceStatus(online) {
  elements.serviceState.className = `service-state ${online ? "online" : "offline"}`;
  elements.serviceState.querySelector("span:last-child").textContent = online
    ? "服务运行正常"
    : "服务连接失败";
}

function showMessage(message = "") {
  elements.formMessage.textContent = message;
  elements.formMessage.hidden = !message;
}

function scrollToLatest() {
  const distanceFromBottom = elements.chatScroll.scrollHeight -
    elements.chatScroll.scrollTop - elements.chatScroll.clientHeight;
  if (distanceFromBottom > 96) return;
  elements.chatScroll.scrollTo({
    top: elements.chatScroll.scrollHeight,
    behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  });
}

function renderTemplate() {
  const template = selectedTemplate();
  if (!template) return;

  const totalSteps = template.sections.reduce((sum, section) => sum + section.steps.length, 0);
  elements.templatePath.textContent = template.display_path || template.path;
  elements.sectionCount.textContent = template.sections.length;
  elements.stepCount.textContent = totalSteps;
  elements.progressCount.textContent = `0 / ${totalSteps}`;
  elements.chatContext.textContent = template.name;
  elements.suggestionButton.textContent = `生成${template.name}`;
  elements.promptInput.placeholder = `输入指令，例如：生成${template.name}`;
  resetConversation();
}

function renderSteps(template) {
  elements.timeline.replaceChildren();
  template.sections.forEach((section, sectionIndex) => {
    const group = document.createElement("section");
    group.className = "step-group";
    const title = document.createElement("h3");
    title.textContent = section.name;
    group.append(title);

    section.steps.forEach((step, stepIndex) => {
      const row = document.createElement("div");
      row.className = "analysis-step";
      row.dataset.key = `${sectionIndex}:${stepIndex}`;
      const text = document.createElement("span");
      text.textContent = step.text;
      const status = document.createElement("span");
      status.className = "step-state";
      status.textContent = "等待";
      row.append(text, status);
      group.append(row);
    });
    elements.timeline.append(group);
  });
}

function resetConversation() {
  if (state.controller) state.controller.abort();
  state.controller = null;
  state.running = false;
  state.report = null;
  elements.welcome.hidden = false;
  elements.conversation.hidden = true;
  elements.reportContent.hidden = true;
  elements.reportContent.replaceChildren();
  elements.reportActions.hidden = true;
  elements.pipelineTitle.textContent = "准备分析";
  elements.conversationTitle.textContent = "新的经营分析";
  elements.conversationState.textContent = "等待提问";
  elements.promptInput.value = "";
  showMessage();

  const ready = Boolean(selectedTemplate());
  elements.suggestionButton.disabled = !ready;
  elements.sendButton.disabled = !ready;
  elements.templateSelect.disabled = !ready;
}

function beginConversation(prompt, template) {
  elements.welcome.hidden = true;
  elements.conversation.hidden = false;
  elements.userMessageText.textContent = prompt;
  elements.assistantIntro.textContent = "我会按照所选模板依次查询数据并整理结论。";
  elements.processDetails.open = true;
  elements.pipelineTitle.textContent = "正在读取模板";
  elements.progressCount.textContent = `0 / ${elements.stepCount.textContent}`;
  elements.conversationTitle.textContent = template.name;
  elements.conversationState.textContent = "分析中";
  elements.reportContent.hidden = true;
  elements.reportContent.replaceChildren();
  elements.reportActions.hidden = true;
  renderSteps(template);
  scrollToLatest();
}

function renderReportSections(sections) {
  elements.reportContent.replaceChildren();
  sections.forEach((section) => {
    if (!section.items.length) return;
    const node = document.createElement("section");
    node.className = "report-section";
    const title = document.createElement("h2");
    title.textContent = section.name;
    const list = document.createElement("ul");
    section.items.forEach((content) => {
      const item = document.createElement("li");
      item.textContent = content;
      list.append(item);
    });
    node.append(title, list);
    elements.reportContent.append(node);
  });
  elements.reportContent.hidden = false;
}

function renderFinalReport(report) {
  renderReportSections(report.section_results.map((section) => ({
    name: section.name,
    items: section.step_results.map((result) => result.content),
  })));
}

async function generateReport(prompt) {
  const template = selectedTemplate();
  if (!template || state.running) return;

  state.running = true;
  state.report = null;
  const controller = new AbortController();
  state.controller = controller;
  elements.sendButton.disabled = true;
  elements.suggestionButton.disabled = true;
  elements.templateSelect.disabled = true;
  showMessage();
  beginConversation(prompt, template);

  const items = template.sections.map((section) => {
    const node = document.createElement("section");
    node.className = "report-section";
    const title = document.createElement("h2");
    title.textContent = section.name;
    const list = document.createElement("ul");
    const rows = section.steps.map(() => {
      const item = document.createElement("li");
      item.hidden = true;
      list.append(item);
      return item;
    });
    node.append(title, list);
    node.hidden = true;
    elements.reportContent.append(node);
    return rows;
  });
  const completed = new Set();
  let payload = null;
  try {
    const response = await fetch("/api/v1/reports/generate/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
      body: JSON.stringify({ template_path: template.path }),
      signal: controller.signal,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(typeof error.detail === "string" ? error.detail : "报告请求失败");
    }
    await consumeEventStream(response, (event, data) => {
      if (state.controller !== controller) return true;
      if (event === "error") throw new Error(data.detail || "报告生成失败");
      if (event === "report_complete") {
        payload = data;
        return true;
      }
      const key = `${data.section_index}:${data.step_index}`;
      const row = elements.timeline.querySelector(`[data-key="${key}"]`);
      const item = items[data.section_index]?.[data.step_index];
      if (!row || !item) return;
      if (event === "phase") {
        row.classList.add("active");
        row.querySelector(".step-state").textContent = data.phase;
        elements.pipelineTitle.textContent = data.phase;
      } else if (event === "conclusion_delta" || event === "step_complete") {
        item.hidden = false;
        item.closest("section").hidden = false;
        elements.reportContent.hidden = false;
        if (event === "conclusion_delta") {
          if (item.dataset.messageId !== data.message_id) item.textContent = "";
          item.dataset.messageId = data.message_id;
          item.textContent += data.text;
        } else {
          item.textContent = data.content;
          completed.add(key);
          row.classList.remove("active");
          row.classList.add("done");
          row.querySelector(".step-state").textContent = "生成结论";
          elements.progressCount.textContent = `${completed.size} / ${elements.stepCount.textContent}`;
        }
      }
      scrollToLatest();
    });
    if (state.controller !== controller) return;
    if (!payload) throw new Error("连接已中断，报告尚未生成完成，请重试。");
    state.report = payload;
    elements.pipelineTitle.textContent = "分析步骤已完成";
    elements.assistantIntro.textContent = "分析完成，报告如下。";
    elements.conversationState.textContent = "已完成";
    elements.processDetails.open = false;
    elements.reportActions.hidden = false;
    renderFinalReport(payload);
    scrollToLatest();
  } catch (error) {
    if (state.controller === controller && error.name !== "AbortError") {
      elements.timeline.querySelectorAll(".analysis-step.active").forEach((row) => row.classList.remove("active"));
      elements.pipelineTitle.textContent = "分析中断";
      elements.conversationState.textContent = "执行失败";
      elements.assistantIntro.textContent = "本次分析未能完成。";
      showMessage(error instanceof Error ? error.message : "报告生成失败");
    }
  } finally {
    if (state.controller === controller) {
      state.running = false;
      state.controller = null;
      elements.sendButton.disabled = false;
      elements.suggestionButton.disabled = false;
      elements.templateSelect.disabled = false;
    }
  }
}

async function loadTemplates() {
  try {
    const [healthResponse, templateResponse] = await Promise.all([
      fetch("/healthz"),
      fetch("/api/v1/report-templates"),
    ]);
    if (!healthResponse.ok || !templateResponse.ok) throw new Error("后端服务不可用");
    const payload = await templateResponse.json();
    state.templates = payload.templates || [];
    if (!state.templates.length) throw new Error("未找到可用的报告模板");

    elements.templateSelect.replaceChildren();
    state.templates.forEach((template, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = template.name;
      elements.templateSelect.append(option);
    });
    elements.templateSelect.disabled = false;
    setServiceStatus(true);
    renderTemplate();
  } catch (error) {
    setServiceStatus(false);
    showMessage(error instanceof Error ? error.message : "页面初始化失败");
    const option = document.createElement("option");
    option.textContent = "模板加载失败";
    elements.templateSelect.replaceChildren(option);
  }
}

elements.templateSelect.addEventListener("change", renderTemplate);
elements.newChatButton.addEventListener("click", resetConversation);
elements.suggestionButton.addEventListener("click", () => {
  const template = selectedTemplate();
  if (template) generateReport(`请生成${template.name}。`);
});
elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const template = selectedTemplate();
  const prompt = elements.promptInput.value.trim() || `请生成${template?.name || "经营分析报告"}。`;
  elements.promptInput.value = "";
  generateReport(prompt);
});
elements.promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});
elements.copyButton.addEventListener("click", async () => {
  if (!state.report) return;
  await navigator.clipboard.writeText(state.report.markdown);
  elements.copyButton.textContent = "已复制";
  window.setTimeout(() => { elements.copyButton.textContent = "复制报告"; }, 1400);
});
elements.downloadButton.addEventListener("click", () => {
  if (!state.report) return;
  const url = URL.createObjectURL(new Blob([state.report.markdown], { type: "text/markdown" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${selectedTemplate()?.name || "分析报告"}.md`;
  link.click();
  URL.revokeObjectURL(url);
});

loadTemplates();
