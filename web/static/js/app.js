const promptEl = document.getElementById("prompt");
const charCountEl = document.getElementById("charCount");
const formEl = document.getElementById("generateForm");
const generateBtn = document.getElementById("generateBtn");
const customizeBtn = document.getElementById("customizeBtn");
const useOnlineImagesEl = document.getElementById("useOnlineImages");
const musicGenreEl = document.getElementById("musicGenre");
const ttsVoiceEl = document.getElementById("ttsVoice");
const scriptEditorSection = document.getElementById("scriptEditorSection");
const editTitle = document.getElementById("editTitle");
const editHook = document.getElementById("editHook");
const scenesEditorList = document.getElementById("scenesEditorList");
const editHashtags = document.getElementById("editHashtags");
const startRenderBtn = document.getElementById("startRenderBtn");
const cancelEditBtn = document.getElementById("cancelEditBtn");

const progressSection = document.getElementById("progressSection");
const progressMessage = document.getElementById("progressMessage");
const progressPercent = document.getElementById("progressPercent");
const progressFill = document.getElementById("progressFill");
const stepList = document.getElementById("stepList");
const errorBox = document.getElementById("errorBox");
const emptyState = document.getElementById("emptyState");
const resultSection = document.getElementById("resultSection");
const resultVideo = document.getElementById("resultVideo");
const resultTitle = document.getElementById("resultTitle");
const resultHook = document.getElementById("resultHook");
const resultTags = document.getElementById("resultTags");
const resultSources = document.getElementById("resultSources");
const downloadBtn = document.getElementById("downloadBtn");
const newShortBtn = document.getElementById("newShortBtn");
const historyList = document.getElementById("historyList");
const refreshHistoryBtn = document.getElementById("refreshHistoryBtn");
const systemStatus = document.getElementById("systemStatus");

let pollTimer = null;
let currentJobId = null;
let currentScript = null;

function updateCharCount() {
  charCountEl.textContent = String(promptEl.value.length);
}

function setGenerating(isGenerating) {
  generateBtn.disabled = isGenerating;
  customizeBtn.disabled = isGenerating;
  generateBtn.innerHTML = isGenerating
    ? '<span class="spinner"></span><span class="btn-label">Generating...</span>'
    : '<span class="btn-label">Quick Generate Video</span>';
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
  errorBox.scrollIntoView({ behavior: "smooth", block: "start" });
}

function hideError() {
  errorBox.classList.add("hidden");
  errorBox.textContent = "";
}

function addStep(message) {
  const li = document.createElement("li");
  li.textContent = message;
  stepList.prepend(li);
}

function updateProgress(progress, message) {
  progressSection.classList.remove("hidden");
  progressMessage.textContent = message;
  progressPercent.textContent = `${progress}%`;
  progressFill.style.width = `${progress}%`;
  addStep(message);
}

function showResult(job) {
  emptyState.classList.add("hidden");
  resultSection.classList.remove("hidden");

  const meta = job.metadata || {};
  resultTitle.textContent = meta.title || "YouTube Short";
  resultHook.textContent = meta.hook || "";
  resultTags.innerHTML = (meta.hashtags || [])
    .map((tag) => `<span class="tag">#${tag.replace(/^#/, "")}</span>`)
    .join("");

  const sources = meta.sources || {};
  resultSources.innerHTML = Object.entries(sources)
    .map(([key, value]) => `<div><strong>${key}:</strong> ${value}</div>`)
    .join("");

  const streamUrl = `/api/stream/${job.id}?t=${Date.now()}`;
  resultVideo.src = streamUrl;
  resultVideo.load();

  downloadBtn.href = `/api/download/${job.id}`;
}

function resetResultPanel() {
  resultSection.classList.add("hidden");
  emptyState.classList.remove("hidden");
  resultVideo.removeAttribute("src");
  progressSection.classList.add("hidden");
  stepList.innerHTML = "";
  progressFill.style.width = "0%";
  hideError();
}

async function pollJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) throw new Error("Failed to fetch job status.");
  const job = await response.json();

  updateProgress(job.progress || 0, job.message || "Working...");

  if (job.status === "completed") {
    clearInterval(pollTimer);
    pollTimer = null;
    setGenerating(false);
    startRenderBtn.disabled = false;
    startRenderBtn.innerHTML = "Generate Video from Edited Script";
    cancelScriptCustomization();
    showResult(job);
    loadHistory();
    return;
  }

  if (job.status === "failed") {
    clearInterval(pollTimer);
    pollTimer = null;
    setGenerating(false);
    startRenderBtn.disabled = false;
    startRenderBtn.innerHTML = "Generate Video from Edited Script";
    showError(job.error || "Generation failed.");
    loadHistory();
  }
}

async function startGeneration(event) {
  event.preventDefault();
  hideError();
  resetResultPanel();

  const prompt = promptEl.value.trim();
  if (prompt.length < 3) {
    showError("Please enter a prompt with at least 3 characters.");
    return;
  }

  setGenerating(true);
  progressSection.classList.remove("hidden");
  updateProgress(0, "Submitting job...");

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        use_online_images: useOnlineImagesEl.checked,
        music_genre: musicGenreEl.value,
        tts_voice: ttsVoiceEl.value,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to start generation.");
    }

    const data = await response.json();
    currentJobId = data.job_id;
    updateProgress(2, "Job queued...");

    pollTimer = setInterval(() => {
      pollJob(currentJobId).catch((error) => {
        clearInterval(pollTimer);
        pollTimer = null;
        setGenerating(false);
        showError(error.message);
      });
    }, 1500);

    await pollJob(currentJobId);
  } catch (error) {
    setGenerating(false);
    showError(error.message);
  }
}

async function fetchScriptForCustomization() {
  hideError();
  const prompt = promptEl.value.trim();
  if (prompt.length < 3) {
    showError("Please enter a prompt with at least 3 characters to write the script.");
    return;
  }

  customizeBtn.disabled = true;
  generateBtn.disabled = true;
  customizeBtn.innerHTML = '<span class="spinner"></span> Writing script...';

  try {
    const response = await fetch("/api/generate-script", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to write script.");
    }

    currentScript = await response.json();
    displayScriptEditor(currentScript);
  } catch (error) {
    showError(error.message);
  } finally {
    customizeBtn.disabled = false;
    generateBtn.disabled = false;
    customizeBtn.innerHTML = '<span class="btn-label">Customize Script First</span>';
  }
}

function displayScriptEditor(script) {
  formEl.classList.add("hidden");
  scriptEditorSection.classList.remove("hidden");

  editTitle.value = script.title || "";
  editHook.value = script.hook || "";
  editHashtags.value = (script.hashtags || []).join(", ");

  scenesEditorList.innerHTML = "";
  script.scenes.forEach((scene, i) => {
    const card = document.createElement("div");
    card.className = "scene-edit-card";
    card.innerHTML = `
      <h4>Scene ${i + 1}</h4>
      <div class="editor-field">
        <label>Voice Narration Text (Spoken audio)</label>
        <textarea data-narration="${i}" rows="2" class="text-input" required>${escapeHtml(scene.narration)}</textarea>
      </div>
      <div class="editor-field">
        <label>Visual Prompt (AI Image generation description)</label>
        <textarea data-visual="${i}" rows="2" class="text-input" required>${escapeHtml(scene.visual_prompt)}</textarea>
      </div>
      <div class="editor-field">
        <label>On-Screen Caption Text (Large bold subtitle overlay)</label>
        <input type="text" data-overlay="${i}" class="text-input" value="${escapeHtml(scene.on_screen_text)}" />
      </div>
    `;
    scenesEditorList.appendChild(card);
  });

  scriptEditorSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelScriptCustomization() {
  scriptEditorSection.classList.add("hidden");
  formEl.classList.remove("hidden");
  currentScript = null;
}

async function renderEditedScript() {
  if (!currentScript) return;

  hideError();
  resetResultPanel();

  const title = editTitle.value.trim();
  const hook = editHook.value.trim();
  const hashtags = editHashtags.value
    .split(",")
    .map((s) => s.trim().replace(/^#/, ""))
    .filter(Boolean);

  const scenes = [];
  const cards = scenesEditorList.querySelectorAll(".scene-edit-card");
  for (let i = 0; i < cards.length; i++) {
    const narration = scenesEditorList.querySelector(`[data-narration="${i}"]`).value.trim();
    const visual_prompt = scenesEditorList.querySelector(`[data-visual="${i}"]`).value.trim();
    const on_screen_text = scenesEditorList.querySelector(`[data-overlay="${i}"]`).value.trim();

    if (!narration || !visual_prompt) {
      showError("Please fill out all narration texts and visual prompts.");
      return;
    }
    scenes.push({ narration, visual_prompt, on_screen_text });
  }

  const updatedScript = {
    title,
    hook,
    scenes,
    hashtags,
  };

  startRenderBtn.disabled = true;
  progressSection.classList.remove("hidden");
  updateProgress(0, "Submitting custom script...");

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: promptEl.value.trim() || title,
        use_online_images: useOnlineImagesEl.checked,
        music_genre: musicGenreEl.value,
        tts_voice: ttsVoiceEl.value,
        script: updatedScript,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to start render job.");
    }

    const data = await response.json();
    currentJobId = data.job_id;
    updateProgress(2, "Rendering job queued...");

    pollTimer = setInterval(() => {
      pollJob(currentJobId).catch((error) => {
        clearInterval(pollTimer);
        pollTimer = null;
        startRenderBtn.disabled = false;
        showError(error.message);
      });
    }, 1500);

    await pollJob(currentJobId);
  } catch (error) {
    startRenderBtn.disabled = false;
    showError(error.message);
  }
}

async function loadHistory() {
  try {
    const response = await fetch("/api/jobs");
    if (!response.ok) return;
    const jobs = await response.json();

    if (!jobs.length) {
      historyList.innerHTML = '<p class="muted">No videos yet. Create your first short above.</p>';
      return;
    }

    historyList.innerHTML = jobs
      .map((job) => {
        const title = job.metadata?.title || job.prompt.slice(0, 60);
        const prompt = job.prompt;
        const actions =
          job.status === "completed"
            ? `<a class="btn btn-ghost" href="/api/download/${job.id}">Download</a>
               <button class="btn btn-ghost" type="button" data-preview="${job.id}">Preview</button>`
            : "";

        return `
          <div class="history-item">
            <div class="history-item-main">
              <div class="history-item-title">${escapeHtml(title)}</div>
              <div class="history-item-prompt">${escapeHtml(prompt)}</div>
            </div>
            <div class="history-item-actions">
              <span class="badge ${job.status}">${job.status}</span>
              ${actions}
            </div>
          </div>`;
      })
      .join("");

    historyList.querySelectorAll("[data-preview]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const jobId = btn.getAttribute("data-preview");
        const response = await fetch(`/api/jobs/${jobId}`);
        if (response.ok) {
          const job = await response.json();
          showResult(job);
          resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  } catch {
    // ignore history errors
  }
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();

    if (!data.ffmpeg) {
      systemStatus.textContent = "ffmpeg nahi mila — install karo";
      systemStatus.className = "status-pill warn";
      return;
    }

    if (data.ollama) {
      systemStatus.textContent = "✅ Ready · Pollinations GPT-4o + Hindi TTS";
      systemStatus.className = "status-pill ok";
    } else {
      systemStatus.textContent = "✅ Ready · Pollinations GPT-4o + Hindi TTS";
      systemStatus.className = "status-pill ok";
    }
  } catch {
    systemStatus.textContent = "Server unreachable";
    systemStatus.className = "status-pill warn";
  }
}

promptEl.addEventListener("input", updateCharCount);
formEl.addEventListener("submit", startGeneration);
customizeBtn.addEventListener("click", fetchScriptForCustomization);
cancelEditBtn.addEventListener("click", cancelScriptCustomization);
startRenderBtn.addEventListener("click", renderEditedScript);

newShortBtn.addEventListener("click", () => {
  promptEl.focus();
  resetResultPanel();
});
refreshHistoryBtn.addEventListener("click", loadHistory);

updateCharCount();
checkHealth();
loadHistory();
