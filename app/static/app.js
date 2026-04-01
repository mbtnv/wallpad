(function () {
  var REFRESH_INTERVAL_MS = 15000;
  var CLOCK_INTERVAL_MS = 1000;
  var PAGE_RELOAD_INTERVAL_MS = 1000 * 60 * 30;
  var ERROR_RELOAD_DELAY_MS = 10000;
  var statusTimer = null;
  var errorReloadTimer = null;
  var dashboardData = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function setText(id, value) {
    var element = byId(id);
    if (!element) {
      return;
    }
    if (value === null || typeof value === "undefined" || value === "") {
      element.textContent = "--";
      return;
    }
    element.textContent = value;
  }

  function showStatus(message, isError) {
    var bar = byId("status-bar");
    if (!bar) {
      return;
    }

    if (!message) {
      bar.style.display = "none";
      bar.textContent = "";
      bar.className = "status";
      return;
    }

    bar.textContent = message;
    bar.className = isError ? "status error" : "status";
    bar.style.display = "block";

    if (statusTimer) {
      window.clearTimeout(statusTimer);
    }

    if (!isError) {
      statusTimer = window.setTimeout(function () {
        showStatus("", false);
      }, 4000);
    }
  }

  function formatClock() {
    var now = new Date();
    var hours = now.getHours();
    var minutes = now.getMinutes();
    var weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
    var months = [
      "January",
      "February",
      "March",
      "April",
      "May",
      "June",
      "July",
      "August",
      "September",
      "October",
      "November",
      "December"
    ];

    setText("clock-time", padNumber(hours) + ":" + padNumber(minutes));
    setText(
      "clock-date",
      weekdays[now.getDay()] + ", " + months[now.getMonth()] + " " + now.getDate()
    );
  }

  function padNumber(value) {
    if (value < 10) {
      return "0" + value;
    }
    return String(value);
  }

  function request(method, url, body, callback) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader("Accept", "application/json");
    if (body) {
      xhr.setRequestHeader("Content-Type", "application/json");
    }

    xhr.onreadystatechange = function () {
      var payload;

      if (xhr.readyState !== 4) {
        return;
      }

      payload = null;
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
          message: "Network error while talking to the dashboard."
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

    if (status >= 500) {
      return "Server error. Please check the backend logs.";
    }

    return "Request failed.";
  }

  function loadDashboard(isInitialLoad) {
    request("GET", "/api/dashboard", null, function (error, payload) {
      if (error) {
        scheduleErrorReload();
        showStatus(error.message + " Reloading page in 10 seconds.", true);
        if (isInitialLoad) {
          renderUnavailableState();
        }
        return;
      }

      clearErrorReload();
      dashboardData = payload;
      renderDashboard(payload);
      showStatus("", false);
    });
  }

  function scheduleErrorReload() {
    if (errorReloadTimer) {
      return;
    }

    errorReloadTimer = window.setTimeout(function () {
      window.location.reload();
    }, ERROR_RELOAD_DELAY_MS);
  }

  function clearErrorReload() {
    if (!errorReloadTimer) {
      return;
    }

    window.clearTimeout(errorReloadTimer);
    errorReloadTimer = null;
  }

  function renderUnavailableState() {
    setText("weather-temp", "--");
    setText("weather-condition", "Dashboard unavailable");
    setText("indoor-temp", "--");
    setText("outdoor-temp", "--");
    setText("heater-state", "--");
    setText("heater-mode", "No connection");
    setText("last-updated", "Unable to load dashboard");
    renderSceneButtons([]);
    renderModeButtons([]);
  }

  function renderDashboard(data) {
    renderWeather(data.weather, data.home);
    renderHeater(data.heater);
    renderSceneButtons(data.scenes || []);
    setLastUpdated(data.generated_at);
  }

  function renderWeather(weather, home) {
    if (weather && weather.available) {
      setText("weather-temp", formatTemperature(weather.temperature, weather.temperature_unit));
      setText("weather-condition", humanize(weather.condition));
    } else {
      setText("weather-temp", "--");
      setText("weather-condition", "Weather unavailable");
    }

    if (home) {
      setText(
        "indoor-temp",
        formatTemperature(home.indoor_temperature, home.indoor_temperature_unit)
      );
      setText(
        "outdoor-temp",
        formatTemperature(home.outdoor_temperature, home.outdoor_temperature_unit)
      );
    }
  }

  function renderHeater(heater) {
    var toggleButton = byId("heater-toggle");
    var heaterName = "Heater";
    var modeText = "Modes unavailable";

    if (heater && heater.friendly_name) {
      heaterName = heater.friendly_name;
    }

    if (!heater || !heater.available) {
      setText("heater-state", heaterName + " offline");
      setText("heater-mode", "No live state");
      if (toggleButton) {
        toggleButton.textContent = "Toggle";
        toggleButton.disabled = true;
      }
      renderModeButtons([]);
      return;
    }

    setText("heater-state", heater.is_on ? "On" : "Off");
    if (heater.mode) {
      modeText = "Mode: " + humanize(heater.mode);
    }
    setText("heater-mode", modeText);

    if (toggleButton) {
      toggleButton.textContent = heater.is_on ? "Turn Off" : "Turn On";
      toggleButton.disabled = false;
      toggleButton.onclick = function () {
        sendAction("POST", "/api/actions/heater/toggle", null, "Heater updated.");
      };
    }

    renderModeButtons(heater.supported_modes || [], heater.mode);
  }

  function renderModeButtons(modes, activeMode) {
    var container = byId("heater-modes");
    var i;
    var button;
    var mode;

    if (!container) {
      return;
    }

    container.innerHTML = "";

    if (!modes || !modes.length) {
      return;
    }

    for (i = 0; i < modes.length; i += 1) {
      mode = modes[i];
      button = document.createElement("button");
      button.type = "button";
      button.className = mode === activeMode ? "mode-active" : "";
      button.appendChild(document.createTextNode(humanize(mode)));
      attachModeHandler(button, mode);
      container.appendChild(button);
    }
  }

  function attachModeHandler(button, mode) {
    button.onclick = function () {
      sendAction(
        "POST",
        "/api/actions/heater/mode",
        { mode: mode },
        "Mode changed to " + humanize(mode) + "."
      );
    };
  }

  function renderSceneButtons(scenes) {
    var container = byId("scene-buttons");
    var i;
    var scene;
    var button;

    if (!container) {
      return;
    }

    container.innerHTML = "";

    if (!scenes || !scenes.length) {
      button = document.createElement("button");
      button.type = "button";
      button.disabled = true;
      button.appendChild(document.createTextNode("No scenes configured"));
      container.appendChild(button);
      return;
    }

    for (i = 0; i < scenes.length; i += 1) {
      scene = scenes[i];
      button = document.createElement("button");
      button.type = "button";
      button.disabled = !scene.available;
      button.appendChild(document.createTextNode(scene.name));
      attachSceneHandler(button, scene.id, scene.available);
      container.appendChild(button);
    }
  }

  function attachSceneHandler(button, sceneId, available) {
    if (!available) {
      return;
    }

    button.onclick = function () {
      sendAction(
        "POST",
        "/api/actions/scene/" + encodeURIComponent(sceneId),
        null,
        "Scene " + humanize(sceneId) + " triggered."
      );
    };
  }

  function sendAction(method, url, body, successMessage) {
    disableButtons(true);
    showStatus("Sending command...", false);

    request(method, url, body, function (error) {
      disableButtons(false);
      if (error) {
        showStatus(error.message, true);
        return;
      }

      showStatus(successMessage, false);
      loadDashboard(false);
    });
  }

  function disableButtons(disabled) {
    var buttons = document.getElementsByTagName("button");
    var i;
    for (i = 0; i < buttons.length; i += 1) {
      buttons[i].disabled = disabled || buttons[i].disabled;
    }
    if (!disabled && dashboardData) {
      renderHeater(dashboardData.heater);
      renderSceneButtons(dashboardData.scenes || []);
    }
  }

  function setLastUpdated(value) {
    if (!value) {
      setText("last-updated", "Last update unknown");
      return;
    }

    setText("last-updated", "Last updated: " + humanizeTimestamp(value));
  }

  function humanizeTimestamp(isoString) {
    var date = new Date(isoString);
    if (isNaN(date.getTime())) {
      return isoString;
    }
    return padNumber(date.getHours()) + ":" + padNumber(date.getMinutes());
  }

  function formatTemperature(value, unit) {
    if (value === null || typeof value === "undefined") {
      return "--";
    }
    return trimZero(Number(value)) + (unit || "");
  }

  function trimZero(value) {
    if (Math.round(value) === value) {
      return String(value);
    }
    return String(Math.round(value * 10) / 10);
  }

  function humanize(value) {
    var parts;
    var i;
    var item;

    if (!value) {
      return "--";
    }

    parts = String(value).replace(/\./g, " ").replace(/_/g, " ").split(" ");
    for (i = 0; i < parts.length; i += 1) {
      item = parts[i];
      if (!item) {
        continue;
      }
      parts[i] = item.charAt(0).toUpperCase() + item.substr(1);
    }
    return parts.join(" ");
  }

  function boot() {
    formatClock();
    window.setInterval(formatClock, CLOCK_INTERVAL_MS);
    loadDashboard(true);
    window.setInterval(function () {
      loadDashboard(false);
    }, REFRESH_INTERVAL_MS);
    window.setInterval(function () {
      window.location.reload();
    }, PAGE_RELOAD_INTERVAL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
}());
