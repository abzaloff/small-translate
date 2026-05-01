(function () {
  const STORAGE_KEYS = {
    enabled: "prompt_translator_enabled",
    source: "prompt_translator_source",
    target: "prompt_translator_target",
    lastDetectedSource: "prompt_translator_last_detected_source",
    lastTarget: "prompt_translator_last_target",
  };

  const BASE_LANGUAGES = [
    "Russian",
    "English",
    "Chinese",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Spanish",
    "Italian",
    "Portuguese",
  ];
  const FROM_LANGUAGES = ["Auto Detect", ...BASE_LANGUAGES];
  const TO_LANGUAGES = [...BASE_LANGUAGES];
  const LIVE_TRANSLATE_DEBOUNCE_MS = 900;
  const VOICE_RESTART_DELAY_MS = 1400;

  const TABS = [
    {
      name: "txt2img",
      promptSelectors: ["#txt2img_prompt textarea", "textarea#txt2img_prompt"],
      negativePromptSelectors: ["#txt2img_neg_prompt textarea", "textarea#txt2img_neg_prompt"],
      generateSelectors: ["#txt2img_generate", "button#txt2img_generate"],
      rootSelectors: ["#txt2img_tab", "#tab_txt2img", "#txt2img"],
    },
    {
      name: "img2img",
      promptSelectors: ["#img2img_prompt textarea", "textarea#img2img_prompt"],
      negativePromptSelectors: ["#img2img_neg_prompt textarea", "textarea#img2img_neg_prompt"],
      generateSelectors: ["#img2img_generate", "button#img2img_generate"],
      rootSelectors: ["#img2img_tab", "#tab_img2img", "#img2img"],
    },
  ];

  const state = {
    rows: new Map(),
    liveTranslateTimers: new Map(),
    voiceSessions: new Map(),
    isInitialized: false,
  };

  function appRoot() {
    if (typeof gradioApp === "function") {
      return gradioApp();
    }
    return document;
  }

  function resolveTabName(tabOrName) {
    if (!tabOrName) {
      return "";
    }
    if (typeof tabOrName === "string") {
      return tabOrName;
    }
    if (typeof tabOrName === "object" && typeof tabOrName.name === "string") {
      return tabOrName.name;
    }
    return "";
  }

  function tabStorageKey(baseKey, tabOrName) {
    const tabName = resolveTabName(tabOrName);
    return tabName ? baseKey + "_" + tabName : baseKey;
  }

  function getStorageValueWithLegacy(tabOrName, baseKey, fallback = "") {
    const scopedKey = tabStorageKey(baseKey, tabOrName);
    const scopedValue = localStorage.getItem(scopedKey);
    if (scopedValue !== null) {
      return scopedValue;
    }
    const legacyValue = localStorage.getItem(baseKey);
    if (legacyValue !== null) {
      return legacyValue;
    }
    return fallback;
  }

  function getStoredEnabled(tabOrName) {
    return getStorageValueWithLegacy(tabOrName, STORAGE_KEYS.enabled, "0") === "1";
  }

  function setStoredEnabled(tabOrName, enabled) {
    localStorage.setItem(tabStorageKey(STORAGE_KEYS.enabled, tabOrName), enabled ? "1" : "0");
  }

  function getStoredSource(tabOrName) {
    const value = getStorageValueWithLegacy(tabOrName, STORAGE_KEYS.source, "Auto Detect");
    return FROM_LANGUAGES.includes(value) ? value : "Auto Detect";
  }

  function setStoredSource(tabOrName, value) {
    localStorage.setItem(tabStorageKey(STORAGE_KEYS.source, tabOrName), value);
  }

  function getStoredTarget(tabOrName) {
    const value = getStorageValueWithLegacy(tabOrName, STORAGE_KEYS.target, "English");
    return TO_LANGUAGES.includes(value) ? value : "English";
  }

  function setStoredTarget(tabOrName, value) {
    localStorage.setItem(tabStorageKey(STORAGE_KEYS.target, tabOrName), value);
  }

  function getLastDetectedSource(tabOrName) {
    const value = getStorageValueWithLegacy(tabOrName, STORAGE_KEYS.lastDetectedSource, "");
    return TO_LANGUAGES.includes(value) ? value : "";
  }

  function setLastDetectedSource(tabOrName, value) {
    if (TO_LANGUAGES.includes(value)) {
      localStorage.setItem(tabStorageKey(STORAGE_KEYS.lastDetectedSource, tabOrName), value);
    }
  }

  function setLastTarget(tabOrName, value) {
    if (TO_LANGUAGES.includes(value)) {
      localStorage.setItem(tabStorageKey(STORAGE_KEYS.lastTarget, tabOrName), value);
    }
  }

  function guessLanguageFromText(text) {
    if (!text || !text.trim()) {
      return "";
    }

    if (/[\u3040-\u30ff]/.test(text)) {
      return "Japanese";
    }
    if (/[\uac00-\ud7af]/.test(text)) {
      return "Korean";
    }
    if (/[\u4e00-\u9fff]/.test(text)) {
      return "Chinese";
    }
    if (/[\u0400-\u04ff]/.test(text)) {
      return "Russian";
    }
    if (/[A-Za-z]/.test(text)) {
      return "English";
    }

    return "";
  }

  function findFirst(selectors) {
    const root = appRoot();
    for (const selector of selectors) {
      const found = root.querySelector(selector);
      if (found) {
        return found;
      }
    }
    return null;
  }

  function isVisible(element) {
    if (!element) {
      return false;
    }
    const style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") {
      return false;
    }
    return element.offsetParent !== null || style.position === "fixed";
  }

  function createLanguageSelect(value, options) {
    const select = document.createElement("select");
    const templateSelect = appRoot().querySelector("select");
    if (templateSelect) {
      select.className = templateSelect.className;
    }
    select.style.minWidth = "120px";
    select.style.height = "var(--input-height)";
    select.style.background = "var(--input-background-fill)";
    select.style.color = "var(--body-text-color)";
    select.style.borderColor = "var(--input-border-color)";
    select.style.borderStyle = "solid";
    select.style.borderWidth = "1px";
    select.style.borderRadius = "var(--radius-lg, 10px)";
    select.style.padding = "0 12px";
    select.style.boxSizing = "border-box";
    select.style.fontSize = "0.95em";
    for (const language of options) {
      const option = document.createElement("option");
      option.value = language;
      option.textContent = language;
      option.selected = language === value;
      select.appendChild(option);
    }
    return select;
  }

  function broadcastSettings(preferredTab) {
    for (const [tabName, row] of state.rows.entries()) {
      if (preferredTab && tabName !== resolveTabName(preferredTab)) {
        continue;
      }
      row.checkbox.checked = getStoredEnabled(tabName);
      row.fromSelect.value = getStoredSource(tabName);
      row.toSelect.value = getStoredTarget(tabName);
    }
  }

  async function translateTabIfEnabled(tab) {
    if (!getStoredEnabled(tab)) {
      return;
    }
    const targetTab = tab || detectActiveTab();
    await translateTabPrompt(targetTab, {
      silent: true,
      suppressInputEvent: true,
      useRememberedSource: true,
    });
  }

  async function swapLanguages(preferredTab) {
    const targetTab = preferredTab || detectActiveTab();
    const source = getStoredSource(targetTab);
    const target = getStoredTarget(targetTab);
    if (source === "Auto Detect") {
      const detected = getLastDetectedSource(targetTab) || "Russian";
      setStoredSource(targetTab, target);
      setStoredTarget(targetTab, detected);
    } else {
      setStoredSource(targetTab, target);
      setStoredTarget(targetTab, source);
    }
    broadcastSettings(targetTab);

    await translateTabIfEnabled(targetTab);
  }

  function applyPromptValue(textarea, value, options = {}) {
    if (textarea.value === value) {
      return;
    }
    if (options.suppressInputEvent === true) {
      textarea.dataset.ptSuppressInputOnce = "1";
    }
    textarea.value = value;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function preserveBoundaryWhitespace(originalText, translatedText) {
    const source = typeof originalText === "string" ? originalText : "";
    const translated = typeof translatedText === "string" ? translatedText : "";

    const leading = (source.match(/^\s+/) || [""])[0];
    const trailing = (source.match(/\s+$/) || [""])[0];

    return leading + translated.trim() + trailing;
  }

  async function callTranslateApi(text, source, target) {
    const payload = { text, source, target };
    const endpoints = [
      "/prompt-translator/translate",
      "/sdapi/v1/prompt-translator/translate",
    ];

    let lastError = null;
    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          lastError = new Error("HTTP " + response.status);
          continue;
        }

        return await response.json();
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error("translate API is unavailable");
  }

  async function translateTabPrompt(tab, options = {}) {
    const promptArea = findFirst(tab.promptSelectors);
    if (!promptArea) {
      if (!options.silent) {
        console.warn("[prompt-translator] prompt area not found for", tab.name);
      }
      return false;
    }

    const source = getStoredSource(tab);
    const target = getStoredTarget(tab);
    const currentText = promptArea.value || "";
    const rememberedDetectedSource = getLastDetectedSource(tab);
    const useRememberedSource =
      source === "Auto Detect" &&
      options &&
      options.useRememberedSource === true &&
      rememberedDetectedSource &&
      rememberedDetectedSource !== target;
    const effectiveSource = useRememberedSource ? rememberedDetectedSource : source;

    if (!currentText.trim() || (effectiveSource !== "Auto Detect" && effectiveSource === target)) {
      return true;
    }
    if (effectiveSource === "Auto Detect") {
      const guessedSource = guessLanguageFromText(currentText);
      if (guessedSource && guessedSource === target) {
        return true;
      }
    }
    try {
      const result = await callTranslateApi(currentText, effectiveSource, target);
      setLastTarget(tab, target);
      let detectedSource = "";
      if (result && typeof result.detected_source === "string" && result.detected_source) {
        detectedSource = result.detected_source;
      } else if (source === "Auto Detect") {
        detectedSource = guessLanguageFromText(currentText);
      }
      if (!detectedSource && useRememberedSource) {
        detectedSource = rememberedDetectedSource;
      }
      if (
        source === "Auto Detect" &&
        useRememberedSource &&
        rememberedDetectedSource &&
        rememberedDetectedSource !== target &&
        detectedSource === target
      ) {
        // Do not overwrite remembered source language with target language in live mixed-text flow.
        detectedSource = rememberedDetectedSource;
      }
      if (detectedSource) {
        setLastDetectedSource(tab, detectedSource);
      }
      if ((promptArea.value || "") !== currentText) {
        // User kept typing while request was in flight; drop stale result.
        return true;
      }
      if (result && typeof result.translated_text === "string") {
        const normalizedTranslatedText = preserveBoundaryWhitespace(
          currentText,
          result.translated_text,
        );
        applyPromptValue(promptArea, normalizedTranslatedText, {
          suppressInputEvent: options && options.suppressInputEvent === true,
        });
      }

      if (result && result.ok === false) {
        console.warn("[prompt-translator] backend error:", result.error || "unknown");
      }
      return true;
    } catch (error) {
      console.warn("[prompt-translator] translation failed:", error);
      return false;
    }
  }

  function detectActiveTab() {
    const focused = document.activeElement;

    for (const tab of TABS) {
      const promptArea = findFirst(tab.promptSelectors);
      if (!promptArea) {
        continue;
      }
      if (promptArea === focused) {
        return tab;
      }
    }

    for (const tab of TABS) {
      const root = findFirst(tab.rootSelectors);
      if (isVisible(root)) {
        return tab;
      }
    }

    return TABS[0];
  }

  function scheduleLiveTranslate(tab) {
    const promptArea = findFirst(tab.promptSelectors);
    if (!promptArea) {
      return;
    }

    if (promptArea.dataset.ptSuppressInputOnce === "1") {
      promptArea.dataset.ptSuppressInputOnce = "0";
      return;
    }

    if (!getStoredEnabled(tab)) {
      return;
    }

    const previousTimer = state.liveTranslateTimers.get(tab.name);
    if (previousTimer) {
      clearTimeout(previousTimer);
    }

    const timer = window.setTimeout(async () => {
      await translateTabPrompt(tab, {
        silent: true,
        suppressInputEvent: true,
        liveMode: true,
        useRememberedSource: true,
      });
      state.liveTranslateTimers.delete(tab.name);
    }, LIVE_TRANSLATE_DEBOUNCE_MS);

    state.liveTranslateTimers.set(tab.name, timer);
  }

  function hookPromptInput(tab) {
    const promptArea = findFirst(tab.promptSelectors);
    if (!promptArea || promptArea.dataset.ptInputHooked === "1") {
      return;
    }

    promptArea.dataset.ptInputHooked = "1";
    promptArea.addEventListener("input", () => {
      scheduleLiveTranslate(tab);
    });
  }

  function getSpeechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function stopVoiceInput(tabName) {
    const session = state.voiceSessions.get(tabName);
    if (!session) {
      return;
    }
    session.keepListening = false;
    session.manualStop = true;
    if (session.restartTimer) {
      clearTimeout(session.restartTimer);
      session.restartTimer = null;
    }
    if (!session.recognition) {
      finalizeVoiceSession(tabName, session);
      return;
    }
    try {
      session.recognition.stop();
    } catch (error) {
      // Ignore stop() errors from stale recognizers.
    }
  }

  function speechLocaleForLanguage(languageName) {
    const normalized = (languageName || "").toLowerCase();
    if (normalized === "russian") return "ru-RU";
    if (normalized === "english") return "en-US";
    if (normalized === "chinese") return "zh-CN";
    if (normalized === "japanese") return "ja-JP";
    if (normalized === "korean") return "ko-KR";
    if (normalized === "german") return "de-DE";
    if (normalized === "french") return "fr-FR";
    if (normalized === "spanish") return "es-ES";
    if (normalized === "italian") return "it-IT";
    if (normalized === "portuguese") return "pt-PT";
    return (navigator && navigator.language) || "en-US";
  }

  function updateVoicePreview(session, interimTranscript) {
    const spokenText = (session.finalTranscript + (interimTranscript || "")).trim();
    session.latestPreview = spokenText
      ? session.baseText + session.baseSuffix + spokenText
      : session.baseText;
    session.promptArea.value = session.latestPreview;
  }

  function appendVoiceChunk(currentText, chunk) {
    const normalizedChunk = typeof chunk === "string" ? chunk.trim() : "";
    if (!normalizedChunk) {
      return currentText || "";
    }
    const base = currentText || "";
    if (!base) {
      return normalizedChunk;
    }
    if (/\s$/.test(base)) {
      return base + normalizedChunk;
    }
    return base + " " + normalizedChunk;
  }

  function finalizeVoiceSession(tabName, session) {
    if (session.restartTimer) {
      clearTimeout(session.restartTimer);
      session.restartTimer = null;
    }
    state.voiceSessions.delete(tabName);
    session.micButton.textContent = session.defaultLabel;
    session.micButton.title = "Voice input";
    if (session.latestPreview !== session.baseText) {
      applyPromptValue(session.promptArea, session.latestPreview);
    }
  }

  function attachRecognitionHandlers(tab, session, recognition) {
    recognition.onresult = (event) => {
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const chunk = result && result[0] && result[0].transcript ? result[0].transcript : "";
        if (!chunk) {
          continue;
        }
        if (result.isFinal) {
          session.finalTranscript = appendVoiceChunk(session.finalTranscript, chunk);
        } else {
          interimTranscript = appendVoiceChunk(interimTranscript, chunk);
        }
      }
      updateVoicePreview(session, interimTranscript);
    };

    recognition.onerror = (event) => {
      if (event && event.error && event.error !== "no-speech" && event.error !== "aborted") {
        console.warn("[prompt-translator] voice input error:", event.error);
      }
    };

    recognition.onend = () => {
      session.recognition = null;
      if (!session.keepListening) {
        finalizeVoiceSession(tab.name, session);
        return;
      }
      session.restartTimer = window.setTimeout(() => {
        if (!session.keepListening || state.voiceSessions.get(tab.name) !== session) {
          return;
        }
        const SpeechRecognitionCtor = getSpeechRecognitionCtor();
        if (!SpeechRecognitionCtor) {
          finalizeVoiceSession(tab.name, session);
          return;
        }
        const nextRecognition = new SpeechRecognitionCtor();
        nextRecognition.lang = speechLocaleForLanguage(getStoredSource(tab));
        nextRecognition.interimResults = true;
        nextRecognition.continuous = false;
        nextRecognition.maxAlternatives = 1;
        session.recognition = nextRecognition;
        session.restartTimer = null;
        attachRecognitionHandlers(tab, session, nextRecognition);
        try {
          nextRecognition.start();
        } catch (error) {
          console.warn("[prompt-translator] voice input restart failed:", error);
          finalizeVoiceSession(tab.name, session);
        }
      }, VOICE_RESTART_DELAY_MS);
    };
  }

  function startVoiceInput(tab, micButton) {
    const SpeechRecognitionCtor = getSpeechRecognitionCtor();
    if (!SpeechRecognitionCtor) {
      console.warn("[prompt-translator] SpeechRecognition is not supported in this browser");
      return;
    }

    const existingSession = state.voiceSessions.get(tab.name);
    if (existingSession) {
      stopVoiceInput(tab.name);
      return;
    }

    const promptArea = findFirst(tab.promptSelectors);
    if (!promptArea) {
      console.warn("[prompt-translator] prompt area not found for voice input:", tab.name);
      return;
    }

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = speechLocaleForLanguage(getStoredSource(tab));
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    const defaultLabel = micButton.dataset.ptDefaultLabel || "🎤";
    micButton.textContent = "■";
    micButton.title = "Stop voice input";

    const baseText = promptArea.value || "";
    const session = {
      recognition,
      keepListening: true,
      manualStop: false,
      restartTimer: null,
      baseText,
      baseSuffix: baseText && !/\s$/.test(baseText) ? " " : "",
      finalTranscript: "",
      latestPreview: baseText,
      promptArea,
      micButton,
      defaultLabel,
    };

    state.voiceSessions.set(tab.name, session);
    attachRecognitionHandlers(tab, session, recognition);
    recognition.start();
  }

  function mountTranslatorRow(tab) {
    if (state.rows.has(tab.name)) {
      const current = state.rows.get(tab.name);
      if (current && current.row && current.row.isConnected) {
        return;
      }
      state.rows.delete(tab.name);
    }

    const promptArea = findFirst(tab.promptSelectors);
    if (!promptArea) {
      return;
    }

    const promptHost = promptArea.closest(".gradio-textbox") || promptArea.parentElement;
    const negativeArea = findFirst(tab.negativePromptSelectors || []);
    const negativeHost = negativeArea
      ? negativeArea.closest(".gradio-textbox") || negativeArea.parentElement
      : null;

    if (!promptHost && !negativeHost) {
      return;
    }

    const row = document.createElement("div");
    row.className = "prompt-translator-row";
    row.dataset.tab = tab.name;
    row.style.display = "flex";
    row.style.alignItems = "center";
    row.style.gap = "8px";
    row.style.flexWrap = "wrap";
    row.style.width = "100%";
    row.style.flex = "0 0 100%";
    row.style.boxSizing = "border-box";
    row.style.margin = "2px 0 8px";

    const label = document.createElement("label");
    label.className = "pt-checkbox-wrap";
    label.style.display = "inline-flex";
    label.style.alignItems = "center";
    label.style.gap = "6px";
    label.style.userSelect = "none";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = getStoredEnabled(tab);

    const checkboxText = document.createElement("span");
    checkboxText.textContent = "Auto Translate";

    label.appendChild(checkbox);
    label.appendChild(checkboxText);

    const fromLabel = document.createElement("span");
    fromLabel.textContent = "From";

    const fromSelect = createLanguageSelect(getStoredSource(tab), FROM_LANGUAGES);

    const swapButton = document.createElement("button");
    swapButton.type = "button";
    swapButton.style.minWidth = "36px";
    swapButton.style.width = "36px";
    swapButton.style.height = "var(--input-height)";
    swapButton.style.display = "inline-flex";
    swapButton.style.alignItems = "center";
    swapButton.style.justifyContent = "center";
    swapButton.style.padding = "0";
    swapButton.style.border = "1px solid var(--button-secondary-border-color, var(--border-color-primary))";
    swapButton.style.borderRadius = "var(--radius-lg, 10px)";
    swapButton.style.background = "var(--button-secondary-background-fill, var(--input-background-fill))";
    swapButton.style.color = "var(--button-secondary-text-color, var(--body-text-color))";
    swapButton.style.cursor = "pointer";
    swapButton.style.textDecoration = "none";
    swapButton.textContent = "↔";

    const toLabel = document.createElement("span");
    toLabel.textContent = "To";

    const toSelect = createLanguageSelect(getStoredTarget(tab), TO_LANGUAGES);

    const translateButton = document.createElement("button");
    translateButton.type = "button";
    translateButton.textContent = "Translate";
    const templatePrimaryButton = findFirst(tab.generateSelectors);
    if (templatePrimaryButton) {
      translateButton.className = templatePrimaryButton.className;
    }
    translateButton.style.height = "var(--input-height)";
    translateButton.style.minHeight = "var(--input-height)";
    translateButton.style.padding = "0 12px";
    translateButton.style.boxSizing = "border-box";
    translateButton.style.display = "inline-flex";
    translateButton.style.alignItems = "center";
    translateButton.style.justifyContent = "center";
    translateButton.style.borderRadius = "var(--radius-lg, 10px)";
    translateButton.style.cursor = "pointer";
    translateButton.style.fontSize = "0.95em";
    translateButton.style.whiteSpace = "nowrap";

    const micButton = document.createElement("button");
    micButton.type = "button";
    micButton.textContent = "🎤";
    micButton.dataset.ptDefaultLabel = "🎤";
    micButton.title = "Voice input";
    const templateSecondaryButton = swapButton;
    if (templateSecondaryButton) {
      micButton.className = templateSecondaryButton.className;
    }
    micButton.style.minWidth = "36px";
    micButton.style.width = "36px";
    micButton.style.height = "var(--input-height)";
    micButton.style.display = "inline-flex";
    micButton.style.alignItems = "center";
    micButton.style.justifyContent = "center";
    micButton.style.padding = "0";
    micButton.style.borderRadius = "var(--radius-lg, 10px)";
    micButton.style.cursor = "pointer";
    micButton.style.lineHeight = "1";
    if (!getSpeechRecognitionCtor()) {
      micButton.disabled = true;
      micButton.title = "Voice input is not supported in this browser";
      micButton.style.opacity = "0.6";
      micButton.style.cursor = "not-allowed";
    }

    const hint = document.createElement("span");
    hint.textContent = "Alt+Q: translate | Alt+W: swap";
    hint.style.opacity = "0.8";
    hint.style.whiteSpace = "nowrap";
    hint.style.fontSize = "0.9em";

    row.appendChild(label);
    row.appendChild(fromLabel);
    row.appendChild(fromSelect);
    row.appendChild(swapButton);
    row.appendChild(toLabel);
    row.appendChild(toSelect);
    row.appendChild(translateButton);
    row.appendChild(micButton);
    row.appendChild(hint);

    if (promptHost && promptHost.parentElement) {
      promptHost.insertAdjacentElement("beforebegin", row);
    } else if (negativeHost && negativeHost.parentElement) {
      negativeHost.insertAdjacentElement("beforebegin", row);
    }

    checkbox.addEventListener("change", async () => {
      setStoredEnabled(tab, checkbox.checked);
      broadcastSettings(tab);

      if (checkbox.checked) {
        await translateTabPrompt(tab, {
          silent: true,
          suppressInputEvent: true,
          useRememberedSource: true,
        });
      }
    });

    fromSelect.addEventListener("change", async () => {
      setStoredSource(tab, fromSelect.value);
      broadcastSettings(tab);
      await translateTabIfEnabled(tab);
    });

    toSelect.addEventListener("change", async () => {
      setStoredTarget(tab, toSelect.value);
      broadcastSettings(tab);
      await translateTabIfEnabled(tab);
    });

    swapButton.addEventListener("click", () => swapLanguages(tab));
    translateButton.addEventListener("click", async () => {
      await translateTabPrompt(tab, { silent: false });
    });
    micButton.addEventListener("click", () => {
      startVoiceInput(tab, micButton);
    });

    state.rows.set(tab.name, {
      row,
      checkbox,
      fromSelect,
      toSelect,
    });
  }

  function hookGenerateButton(tab) {
    const button = findFirst(tab.generateSelectors);
    if (!button || button.dataset.ptHooked === "1") {
      return;
    }

    button.dataset.ptHooked = "1";

    button.addEventListener(
      "click",
      async (event) => {
        if (button.dataset.ptBypass === "1") {
          button.dataset.ptBypass = "0";
          return;
        }

        if (!getStoredEnabled(tab)) {
          return;
        }

        event.preventDefault();
        event.stopImmediatePropagation();

        await translateTabPrompt(tab, { silent: false });

        button.dataset.ptBypass = "1";
        button.click();
      },
      true,
    );
  }

  function initializeUi() {
    for (const tab of TABS) {
      mountTranslatorRow(tab);
      hookGenerateButton(tab);
      hookPromptInput(tab);
    }

    broadcastSettings();
  }

  function hookHotkey() {
    if (window.__promptTranslatorHotkeyHooked) {
      return;
    }

    window.__promptTranslatorHotkeyHooked = true;

    document.addEventListener("keydown", async (event) => {
      if (!event.altKey || event.shiftKey || event.ctrlKey || event.metaKey) {
        return;
      }

      const key = (event.key || "").toLowerCase();
      const isTranslateHotkey = event.code === "KeyQ" || key === "q";
      const isSwapHotkey = event.code === "KeyW" || key === "w";

      if (!isTranslateHotkey && !isSwapHotkey) {
        return;
      }

      event.preventDefault();

      if (isSwapHotkey) {
        swapLanguages();
        return;
      }

      const activeTab = detectActiveTab();
      await translateTabPrompt(activeTab, { silent: false });
    });
  }

  function boot() {
    // Keep extension active in UI, and reset controls to defaults on each UI load.
    for (const tab of TABS) {
      setStoredEnabled(tab, false);
      setStoredSource(tab, "Auto Detect");
      setStoredTarget(tab, "English");
      localStorage.removeItem(tabStorageKey(STORAGE_KEYS.lastDetectedSource, tab));
      if (!localStorage.getItem(tabStorageKey(STORAGE_KEYS.lastTarget, tab))) {
        setLastTarget(tab, "English");
      }
    }

    initializeUi();
    hookHotkey();

    if (state.isInitialized) {
      return;
    }

    state.isInitialized = true;
    const observer = new MutationObserver(() => {
      initializeUi();
    });

    observer.observe(appRoot(), { childList: true, subtree: true });
  }

  if (typeof onUiLoaded === "function") {
    onUiLoaded(boot);
  } else {
    window.addEventListener("DOMContentLoaded", boot);
  }
})();

