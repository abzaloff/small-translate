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
    isInitialized: false,
  };

  function appRoot() {
    if (typeof gradioApp === "function") {
      return gradioApp();
    }
    return document;
  }

  function getStoredEnabled() {
    return localStorage.getItem(STORAGE_KEYS.enabled) === "1";
  }

  function getStoredSource() {
    const value = localStorage.getItem(STORAGE_KEYS.source) || "Auto Detect";
    return FROM_LANGUAGES.includes(value) ? value : "Auto Detect";
  }

  function getStoredTarget() {
    const value = localStorage.getItem(STORAGE_KEYS.target) || "English";
    return TO_LANGUAGES.includes(value) ? value : "English";
  }

  function getLastDetectedSource() {
    const value = localStorage.getItem(STORAGE_KEYS.lastDetectedSource) || "";
    return TO_LANGUAGES.includes(value) ? value : "";
  }

  function setLastDetectedSource(value) {
    if (TO_LANGUAGES.includes(value)) {
      localStorage.setItem(STORAGE_KEYS.lastDetectedSource, value);
    }
  }

  function setLastTarget(value) {
    if (TO_LANGUAGES.includes(value)) {
      localStorage.setItem(STORAGE_KEYS.lastTarget, value);
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

  function broadcastSettings() {
    const enabled = getStoredEnabled();
    const source = getStoredSource();
    const target = getStoredTarget();

    for (const row of state.rows.values()) {
      row.checkbox.checked = enabled;
      row.fromSelect.value = source;
      row.toSelect.value = target;
    }
  }

  async function swapLanguages() {
    const source = getStoredSource();
    const target = getStoredTarget();
    if (source === "Auto Detect") {
      const detected = getLastDetectedSource() || "Russian";
      localStorage.setItem(STORAGE_KEYS.source, target);
      localStorage.setItem(STORAGE_KEYS.target, detected);
    } else {
      localStorage.setItem(STORAGE_KEYS.source, target);
      localStorage.setItem(STORAGE_KEYS.target, source);
    }
    broadcastSettings();

    if (getStoredEnabled()) {
      const activeTab = detectActiveTab();
      await translateTabPrompt(activeTab, {
        silent: true,
        suppressInputEvent: true,
        useRememberedSource: true,
      });
    }
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

    const source = getStoredSource();
    const target = getStoredTarget();
    const currentText = promptArea.value || "";
    const rememberedDetectedSource = getLastDetectedSource();
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
      setLastTarget(target);
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
        setLastDetectedSource(detectedSource);
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

    if (!getStoredEnabled()) {
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
    checkbox.checked = getStoredEnabled();

    const checkboxText = document.createElement("span");
    checkboxText.textContent = "Auto Translate";

    label.appendChild(checkbox);
    label.appendChild(checkboxText);

    const fromLabel = document.createElement("span");
    fromLabel.textContent = "From";

    const fromSelect = createLanguageSelect(getStoredSource(), FROM_LANGUAGES);

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

    const toSelect = createLanguageSelect(getStoredTarget(), TO_LANGUAGES);

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
    row.appendChild(hint);

    if (negativeHost && negativeHost.parentElement) {
      negativeHost.insertAdjacentElement("beforebegin", row);
    } else if (promptHost && promptHost.parentElement) {
      promptHost.insertAdjacentElement("afterend", row);
    }

    checkbox.addEventListener("change", async () => {
      localStorage.setItem(STORAGE_KEYS.enabled, checkbox.checked ? "1" : "0");
      broadcastSettings();

      if (checkbox.checked) {
        await translateTabPrompt(tab, {
          silent: true,
          suppressInputEvent: true,
          useRememberedSource: true,
        });
      }
    });

    fromSelect.addEventListener("change", () => {
      localStorage.setItem(STORAGE_KEYS.source, fromSelect.value);
      broadcastSettings();
    });

    toSelect.addEventListener("change", () => {
      localStorage.setItem(STORAGE_KEYS.target, toSelect.value);
      broadcastSettings();
    });

    swapButton.addEventListener("click", swapLanguages);

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

        if (!getStoredEnabled()) {
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
    localStorage.setItem(STORAGE_KEYS.enabled, "0");
    localStorage.setItem(STORAGE_KEYS.source, "Auto Detect");
    localStorage.setItem(STORAGE_KEYS.target, "English");
    localStorage.removeItem(STORAGE_KEYS.lastDetectedSource);
    if (!localStorage.getItem(STORAGE_KEYS.lastTarget)) {
      localStorage.setItem(STORAGE_KEYS.lastTarget, "English");
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

