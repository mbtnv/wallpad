(function () {
  var currentVersion = null;
  var loadedContent = "";
  var pendingRequestCount = 0;
  var statusTimer = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function request(method, url, body, callback) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader("Accept", "application/json");
    if (body) {
      xhr.setRequestHeader("Content-Type", "application/json");
    }

    xhr.onreadystatechange = function () {
      var payload = null;

      if (xhr.readyState !== 4) {
        return;
      }

      if (xhr.responseText) {
        try {
          payload = JSON.parse(xhr.responseText);
        } catch (error) {
          payload = null;
        }
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        callback(null, payload);
        return;
      }

      callback(
        {
          status: xhr.status,
          message: extractErrorMessage(payload, xhr.status)
        },
        payload
      );
    };

    xhr.onerror = function () {
      callback(
        {
          status: 0,
          message: "Network error while talking to the config editor."
        },
        null
      );
    };

    xhr.send(body ? JSON.stringify(body) : null);
  }

  function extractErrorMessage(payload, status) {
    if (payload && payload.detail) {
      if (typeof payload.detail === "string") {
        return payload.detail;
      }
      if (payload.detail.message) {
        return payload.detail.message;
      }
    }

    if (status === 401) {
      return "Authentication failed for the config editor.";
    }

    if (status === 409) {
      return "The file changed on the server. Reload before saving again.";
    }

    if (status >= 500) {
      return "Server error. Please check the backend logs.";
    }

    return "Request failed.";
  }

  function showStatus(message, isError) {
    var status = byId("editor-status");
    if (!status) {
      return;
    }

    if (!message) {
      status.style.display = "none";
      status.textContent = "";
      status.className = "status";
      return;
    }

    status.style.display = "block";
    status.textContent = message;
    status.className = isError ? "status error" : "status";

    if (statusTimer) {
      window.clearTimeout(statusTimer);
    }

    if (!isError) {
      statusTimer = window.setTimeout(function () {
        showStatus("", false);
      }, 4000);
    }
  }

  function setBusy(isBusy) {
    pendingRequestCount = isBusy ? pendingRequestCount + 1 : Math.max(0, pendingRequestCount - 1);

    var reloadButton = byId("reload-button");
    var validateButton = byId("validate-button");
    var saveButton = byId("save-button");
    var editor = byId("config-editor");
    var disabled = pendingRequestCount > 0;

    if (reloadButton) {
      reloadButton.disabled = disabled;
    }
    if (validateButton) {
      validateButton.disabled = disabled;
    }
    if (saveButton) {
      saveButton.disabled = disabled;
    }
    if (editor) {
      editor.disabled = disabled;
    }
  }

  function currentContent() {
    var editor = byId("config-editor");
    return editor ? editor.value : "";
  }

  function hasUnsavedChanges() {
    return currentContent() !== loadedContent;
  }

  function updateDirtyState() {
    var dirtyState = byId("editor-dirty");
    if (!dirtyState) {
      return;
    }

    dirtyState.textContent = hasUnsavedChanges() ? "State: unsaved changes" : "State: clean";
    dirtyState.className = hasUnsavedChanges()
      ? "editor-meta-pill editor-meta-pill-warning"
      : "editor-meta-pill";
  }

  function updateMeta(payload) {
    var version = byId("editor-version");
    var validation = byId("editor-validation");

    if (version) {
      version.textContent = "Version: " + (payload && payload.version ? payload.version : "--");
    }

    if (!validation) {
      return;
    }

    if (!payload) {
      validation.textContent = "Validation: unavailable";
      validation.className = "editor-meta-pill editor-meta-pill-danger";
      return;
    }

    if (payload.is_valid) {
      validation.textContent = "Validation: valid";
      validation.className = "editor-meta-pill editor-meta-pill-success";
      return;
    }

    validation.textContent = "Validation: invalid";
    validation.className = "editor-meta-pill editor-meta-pill-danger";
  }

  function applyDocument(payload) {
    var editor = byId("config-editor");
    if (!editor || !payload) {
      return;
    }

    editor.value = payload.content || "";
    loadedContent = editor.value;
    currentVersion = payload.version || null;
    updateMeta(payload);
    updateDirtyState();

    if (payload.validation_error) {
      showStatus(payload.validation_error, true);
      return;
    }

    showStatus("", false);
  }

  function loadDocument() {
    setBusy(true);
    request("GET", "/api/config", null, function (error, payload) {
      setBusy(false);
      if (error) {
        showStatus(error.message, true);
        updateMeta(null);
        return;
      }

      applyDocument(payload);
      showStatus("Config loaded.", false);
    });
  }

  function validateDocument() {
    setBusy(true);
    request(
      "POST",
      "/api/config/validate",
      { content: currentContent() },
      function (error, payload) {
        setBusy(false);
        if (error) {
          showStatus(error.message, true);
          return;
        }

        updateMeta(payload);
        updateDirtyState();

        if (payload && payload.validation_error) {
          showStatus(payload.validation_error, true);
          return;
        }

        showStatus("Config is valid.", false);
      }
    );
  }

  function saveDocument() {
    setBusy(true);
    request(
      "PUT",
      "/api/config",
      {
        content: currentContent(),
        version: currentVersion
      },
      function (error, payload) {
        setBusy(false);
        if (error) {
          showStatus(error.message, true);
          return;
        }

        applyDocument(payload);
        showStatus(payload && payload.message ? payload.message : "Config saved.", false);
      }
    );
  }

  function handleEditorKeydown(event) {
    var isSaveShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s";
    if (!isSaveShortcut) {
      return;
    }

    event.preventDefault();
    saveDocument();
  }

  function bindEvents() {
    var editor = byId("config-editor");
    var reloadButton = byId("reload-button");
    var validateButton = byId("validate-button");
    var saveButton = byId("save-button");

    if (editor) {
      editor.addEventListener("input", updateDirtyState);
      editor.addEventListener("keydown", handleEditorKeydown);
    }

    if (reloadButton) {
      reloadButton.addEventListener("click", function () {
        if (hasUnsavedChanges() && !window.confirm("Discard local changes and reload from server?")) {
          return;
        }
        loadDocument();
      });
    }

    if (validateButton) {
      validateButton.addEventListener("click", validateDocument);
    }

    if (saveButton) {
      saveButton.addEventListener("click", saveDocument);
    }

    window.addEventListener("beforeunload", function (event) {
      if (!hasUnsavedChanges()) {
        return;
      }

      event.preventDefault();
      event.returnValue = "";
    });
  }

  bindEvents();
  loadDocument();
})();
