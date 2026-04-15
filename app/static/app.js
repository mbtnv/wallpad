(function () {
  var REFRESH_INTERVAL_MS = 15000;
  var CLOCK_INTERVAL_MS = 1000;
  var PAGE_RELOAD_INTERVAL_MS = 1000 * 60 * 30;
  var ERROR_RELOAD_DELAY_MS = 10000;
  var CONFIG_RELOAD_DELAY_MS = 600;
  var PAGE_ANIMATION_DURATION_MS = 220;
  var SWIPE_THRESHOLD_PX = 56;
  var SWIPE_DOMINANCE_RATIO = 1.25;
  var ACTIVE_PAGE_STORAGE_KEY = "wallpad-active-page";
  var statusTimer = null;
  var errorReloadTimer = null;
  var dashboardData = null;
  var activePageId = null;
  var dashboardConfigVersion = null;
  var pageAnimationResetTimer = null;
  var pageSwipeHandlersBound = false;
  var pageSwipeState = null;
  var dashboardFitFrame = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function ensurePageLayout() {
    var app = document.querySelector(".app");
    var statusBar = byId("status-bar");
    var pageContent = byId("page-content");
    var pageHeader = byId("page-header");
    var panels = byId("panels");
    var footer = document.querySelector(".footer");
    var legacyHero = document.querySelector(".hero");

    if (!app || !panels) {
      return;
    }

    if (!pageContent) {
      pageContent = document.createElement("div");
      pageContent.id = "page-content";
      pageContent.className = "page-content";

      if (statusBar && statusBar.parentNode === app) {
        app.insertBefore(pageContent, statusBar.nextSibling);
      } else if (footer && footer.parentNode === app) {
        app.insertBefore(pageContent, footer);
      } else {
        app.appendChild(pageContent);
      }
    }

    if (!pageHeader) {
      pageHeader = document.createElement("div");
      pageHeader.id = "page-header";
      pageHeader.className = "page-header";
      pageHeader.style.display = "none";
      pageContent.insertBefore(pageHeader, pageContent.firstChild);
    }

    if (panels.parentNode !== pageContent) {
      pageContent.appendChild(panels);
    }

    if (legacyHero && legacyHero.parentNode) {
      legacyHero.parentNode.removeChild(legacyHero);
    }
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

  function setNodeText(node, value) {
    if (!node) {
      return;
    }
    if (value === null || typeof value === "undefined" || value === "") {
      node.textContent = "--";
      return;
    }
    node.textContent = value;
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
      scheduleDashboardFit();
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

    scheduleDashboardFit();
  }

  function formatClock() {
    var clockWidgets = document.querySelectorAll("[data-clock-widget]");
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
    var timeText = padNumber(hours) + ":" + padNumber(minutes);
    var weekdayText = weekdays[now.getDay()];
    var dateText = months[now.getMonth()] + " " + now.getDate();
    var i;
    var widget;

    for (i = 0; i < clockWidgets.length; i += 1) {
      widget = clockWidgets[i];
      setNodeText(widget.querySelector("[data-clock-part='time']"), timeText);
      setNodeText(widget.querySelector("[data-clock-part='weekday']"), weekdayText);
      setNodeText(widget.querySelector("[data-clock-part='date']"), dateText);
    }
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
      handleDashboardPayload(payload);
    });
  }

  function handleDashboardPayload(payload) {
    if (
      dashboardConfigVersion &&
      payload &&
      payload.config_version &&
      dashboardConfigVersion !== payload.config_version
    ) {
      showStatus("Dashboard config updated. Reloading...", false);
      window.setTimeout(function () {
        window.location.reload();
      }, CONFIG_RELOAD_DELAY_MS);
      return;
    }

    dashboardConfigVersion = payload ? payload.config_version : dashboardConfigVersion;
    dashboardData = payload;
    renderDashboard(payload);

    if (payload && payload.config_error) {
      showStatus(payload.config_error, true);
      return;
    }

    showStatus("", false);
  }

  function getViewportWidth() {
    if (window.visualViewport && window.visualViewport.width) {
      return window.visualViewport.width;
    }

    return window.innerWidth || document.documentElement.clientWidth || 0;
  }

  function getViewportHeight() {
    if (window.visualViewport && window.visualViewport.height) {
      return window.visualViewport.height;
    }

    return window.innerHeight || document.documentElement.clientHeight || 0;
  }

  function syncDashboardViewport() {
    var root = document.documentElement;
    var viewportHeight = getViewportHeight();

    if (!root || !viewportHeight) {
      return;
    }

    root.style.setProperty("--dashboard-viewport-height", viewportHeight + "px");
  }

  function fitDashboardToViewport() {
    var app = document.querySelector(".app");
    var viewportWidth;
    var viewportHeight;
    var naturalWidth;
    var naturalHeight;
    var scale;

    if (!app) {
      return;
    }

    syncDashboardViewport();
    app.style.setProperty("--dashboard-scale", "1");

    viewportWidth = getViewportWidth();
    viewportHeight = getViewportHeight();
    naturalWidth = Math.max(app.offsetWidth, app.scrollWidth);
    naturalHeight = Math.max(app.offsetHeight, app.scrollHeight);

    if (!viewportWidth || !viewportHeight || !naturalWidth || !naturalHeight) {
      return;
    }

    scale = Math.min(1, viewportWidth / naturalWidth, viewportHeight / naturalHeight);

    if (scale > 0.995) {
      scale = 1;
    }

    app.style.setProperty("--dashboard-scale", scale.toFixed(4));
  }

  function scheduleDashboardFit() {
    syncDashboardViewport();

    if (dashboardFitFrame) {
      window.cancelAnimationFrame(dashboardFitFrame);
    }

    dashboardFitFrame = window.requestAnimationFrame(function () {
      dashboardFitFrame = null;
      fitDashboardToViewport();
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
    renderDashboard({
      generated_at: null,
      default_page: "offline",
      pages: [
        {
          id: "offline",
          title: "Offline",
          widgets: [
            {
              id: "offline-state",
              type: "sensor",
              title: "Dashboard",
              primary_text: "--",
              secondary_text: "Dashboard unavailable",
              rows: [],
              actions: []
            }
          ]
        }
      ]
    });
  }

  function renderDashboard(data, options) {
    var pages = (data && data.pages) || [];
    var selectedPageId = resolveActivePageId(pages, data ? data.default_page : null);
    var page = findPage(pages, selectedPageId);
    var pageTransition = null;

    activePageId = selectedPageId;
    saveActivePageId(selectedPageId);

    if (options && options.transitionDirection) {
      pageTransition = { direction: options.transitionDirection };
    }

    renderPageTabs(pages, selectedPageId);
    renderPage(page, pageTransition);
    setLastUpdated(data ? data.generated_at : null);
    scheduleDashboardFit();
  }

  function resolveActivePageId(pages, defaultPageId) {
    var storedPageId = activePageId || loadSavedPageId();
    var fallbackPageId = defaultPageId;

    if (hasPage(pages, storedPageId)) {
      return storedPageId;
    }

    if (hasPage(pages, fallbackPageId)) {
      return fallbackPageId;
    }

    if (pages.length) {
      return pages[0].id;
    }

    return null;
  }

  function hasPage(pages, pageId) {
    return !!findPage(pages, pageId);
  }

  function findPage(pages, pageId) {
    var i;
    if (!pageId) {
      return null;
    }
    for (i = 0; i < pages.length; i += 1) {
      if (pages[i].id === pageId) {
        return pages[i];
      }
    }
    return null;
  }

  function renderPageTabs(pages, selectedPageId) {
    var container = byId("page-tabs");
    var i;
    var page;
    var button;

    if (!container) {
      return;
    }

    container.innerHTML = "";

    if (!pages || pages.length <= 1) {
      container.style.display = "none";
      return;
    }

    container.style.display = "flex";

    for (i = 0; i < pages.length; i += 1) {
      page = pages[i];
      button = document.createElement("button");
      button.type = "button";
      button.className = "page-tab" + (page.id === selectedPageId ? " active" : "");
      button.appendChild(document.createTextNode(page.title));
      attachPageHandler(button, page.id);
      container.appendChild(button);
    }
  }

  function attachPageHandler(button, pageId) {
    button.onclick = function () {
      setActivePage(pageId);
    };
  }

  function setActivePage(pageId, transitionDirection) {
    var pages = (dashboardData && dashboardData.pages) || [];
    var resolvedTransitionDirection = transitionDirection;

    if (!pageId) {
      return;
    }

    if (pages.length && !hasPage(pages, pageId)) {
      return;
    }

    if (pageId === activePageId) {
      return;
    }

    if (!resolvedTransitionDirection) {
      resolvedTransitionDirection = resolvePageTransitionDirection(pages, activePageId, pageId);
    }

    activePageId = pageId;
    saveActivePageId(pageId);

    if (dashboardData) {
      renderDashboard(dashboardData, {
        transitionDirection: resolvedTransitionDirection
      });
    }
  }

  function setActivePageByOffset(offset) {
    var pages = (dashboardData && dashboardData.pages) || [];
    var currentIndex = findPageIndex(pages, activePageId);
    var nextIndex;

    if (!offset || pages.length <= 1 || currentIndex < 0) {
      return;
    }

    nextIndex = currentIndex + offset;
    if (nextIndex < 0 || nextIndex >= pages.length) {
      return;
    }

    setActivePage(pages[nextIndex].id, offset > 0 ? 1 : -1);
  }

  function findPageIndex(pages, pageId) {
    var i;

    if (!pageId) {
      return -1;
    }

    for (i = 0; i < pages.length; i += 1) {
      if (pages[i].id === pageId) {
        return i;
      }
    }

    return -1;
  }

  function resolvePageTransitionDirection(pages, currentPageId, nextPageId) {
    var currentIndex = findPageIndex(pages, currentPageId);
    var nextIndex = findPageIndex(pages, nextPageId);

    if (currentIndex < 0 || nextIndex < 0 || currentIndex === nextIndex) {
      return 0;
    }

    return nextIndex > currentIndex ? 1 : -1;
  }

  function isSwipeEnabled() {
    return !!(dashboardData && dashboardData.swipe_enabled);
  }

  function bindPageSwipeHandlers() {
    ensurePageLayout();
    var container = byId("page-content");

    if (!container || pageSwipeHandlersBound) {
      return;
    }

    pageSwipeHandlersBound = true;
    container.addEventListener("touchstart", handlePageTouchStart, false);
    container.addEventListener("touchmove", handlePageTouchMove, false);
    container.addEventListener("touchend", handlePageTouchEnd, false);
    container.addEventListener("touchcancel", resetPageTouchState, false);
  }

  function handlePageTouchStart(event) {
    var touch;

    if (
      !isSwipeEnabled() ||
      !event.touches ||
      event.touches.length !== 1 ||
      isInteractiveTarget(event.target)
    ) {
      resetPageTouchState();
      return;
    }

    touch = event.touches[0];
    pageSwipeState = {
      startX: touch.clientX,
      startY: touch.clientY,
      currentX: touch.clientX,
      currentY: touch.clientY
    };
  }

  function handlePageTouchMove(event) {
    var touch;

    if (!pageSwipeState) {
      return;
    }

    if (!event.touches || event.touches.length !== 1) {
      resetPageTouchState();
      return;
    }

    touch = event.touches[0];
    pageSwipeState.currentX = touch.clientX;
    pageSwipeState.currentY = touch.clientY;

    if (event.cancelable) {
      event.preventDefault();
    }
  }

  function handlePageTouchEnd(event) {
    var touch;
    var deltaX;
    var deltaY;

    if (!pageSwipeState) {
      return;
    }

    if (event.changedTouches && event.changedTouches.length) {
      touch = event.changedTouches[0];
      pageSwipeState.currentX = touch.clientX;
      pageSwipeState.currentY = touch.clientY;
    }

    deltaX = pageSwipeState.currentX - pageSwipeState.startX;
    deltaY = pageSwipeState.currentY - pageSwipeState.startY;
    resetPageTouchState();

    if (Math.abs(deltaX) < SWIPE_THRESHOLD_PX) {
      return;
    }

    if (Math.abs(deltaX) <= Math.abs(deltaY) * SWIPE_DOMINANCE_RATIO) {
      return;
    }

    setActivePageByOffset(deltaX < 0 ? 1 : -1);
  }

  function resetPageTouchState() {
    pageSwipeState = null;
  }

  function isInteractiveTarget(node) {
    var current = node;
    var tagName;

    while (current && current !== document.body) {
      if (current.nodeType === 1) {
        tagName = current.tagName ? current.tagName.toLowerCase() : "";
        if (
          tagName === "button" ||
          tagName === "a" ||
          tagName === "input" ||
          tagName === "select" ||
          tagName === "textarea"
        ) {
          return true;
        }
      }
      current = current.parentNode;
    }

    return false;
  }

  function resolveWidgetPlacement(widget) {
    if (widget && widget.placement === "header") {
      return "header";
    }
    return "content";
  }

  function renderPage(page, pageTransition) {
    ensurePageLayout();
    var pageContent = byId("page-content");
    var header = byId("page-header");
    var panels = byId("panels");
    var widgets = (page && page.widgets) || [];
    var headerWidgets = [];
    var contentWidgets = [];
    var widget;
    var i;

    if (!pageContent || !header || !panels) {
      return;
    }

    clearPageAnimation(pageContent);
    header.innerHTML = "";
    panels.innerHTML = "";

    for (i = 0; i < widgets.length; i += 1) {
      widget = widgets[i];
      if (resolveWidgetPlacement(widget) === "header") {
        headerWidgets.push(widget);
      } else {
        contentWidgets.push(widget);
      }
    }

    if (headerWidgets.length) {
      header.style.display = "flex";
      for (i = 0; i < headerWidgets.length; i += 1) {
        header.appendChild(buildWidget(headerWidgets[i]));
      }
    } else {
      header.style.display = "none";
    }

    if (!headerWidgets.length && !contentWidgets.length) {
      panels.appendChild(buildEmptyState());
      formatClock();
      applyPageAnimation(pageContent, pageTransition);
      return;
    }

    for (i = 0; i < contentWidgets.length; i += 1) {
      panels.appendChild(buildWidget(contentWidgets[i]));
    }

    formatClock();
    applyPageAnimation(pageContent, pageTransition);
  }

  function applyPageAnimation(container, pageTransition) {
    var className;

    if (!container || !pageTransition || !pageTransition.direction) {
      return;
    }

    className = pageTransition.direction > 0 ? "panels-animate-next" : "panels-animate-prev";

    void container.offsetWidth;
    container.classList.add(className);

    pageAnimationResetTimer = window.setTimeout(function () {
      clearPageAnimation(container);
    }, PAGE_ANIMATION_DURATION_MS);
  }

  function clearPageAnimation(container) {
    if (pageAnimationResetTimer) {
      window.clearTimeout(pageAnimationResetTimer);
      pageAnimationResetTimer = null;
    }

    if (!container) {
      return;
    }

    container.classList.remove("panels-animate-next");
    container.classList.remove("panels-animate-prev");
  }

  function buildEmptyState() {
    var panel = document.createElement("section");
    var title = document.createElement("h2");
    var subtitle = document.createElement("div");

    panel.className = "panel panel-wide";
    title.appendChild(document.createTextNode("No widgets configured"));
    subtitle.className = "muted";
    subtitle.appendChild(document.createTextNode("Add widgets to this page in dashboard.yaml."));

    panel.appendChild(title);
    panel.appendChild(subtitle);
    return panel;
  }

  function appendWidgetTitle(panel, value) {
    var title;

    if (!value) {
      return;
    }

    title = document.createElement("h2");
    title.appendChild(document.createTextNode(value));
    panel.appendChild(title);
  }

  function buildClockWidget(widget) {
    var panel = document.createElement("section");
    var placement = resolveWidgetPlacement(widget);
    var time = document.createElement("div");
    var meta = document.createElement("div");
    var weekday = document.createElement("div");
    var date = document.createElement("div");

    panel.className =
      "panel panel-clock" +
      (widget.wide ? " panel-wide" : "") +
      (placement === "header" ? " panel-clock-header" : " panel-clock-content") +
      (!widget.wide && placement !== "header" ? " panel-clock-compact" : "");
    panel.setAttribute("data-clock-widget", "true");

    appendWidgetTitle(panel, widget.title);

    time.className = "clock-widget-time";
    time.setAttribute("data-clock-part", "time");
    time.appendChild(document.createTextNode("--:--"));
    panel.appendChild(time);

    meta.className = "clock-widget-meta";

    weekday.className = "clock-widget-weekday";
    weekday.setAttribute("data-clock-part", "weekday");
    weekday.appendChild(document.createTextNode("Loading weekday..."));
    meta.appendChild(weekday);

    date.className = "clock-widget-date";
    date.setAttribute("data-clock-part", "date");
    date.appendChild(document.createTextNode("Loading date..."));
    meta.appendChild(date);

    panel.appendChild(meta);
    return panel;
  }

  function buildWidget(widget) {
    var panel = document.createElement("section");
    var primary;
    var secondary;
    var historyContainer;
    var rowContainer;
    var forecastContainer;
    var actionsContainer;
    var i;

    if (widget && widget.type === "clock") {
      return buildClockWidget(widget);
    }

    panel.className = "panel" + (widget.wide ? " panel-wide" : "");
    appendWidgetTitle(panel, widget.title || "Widget");

    if (widget.primary_text !== null && typeof widget.primary_text !== "undefined") {
      primary = document.createElement("div");
      primary.className = "big-value";
      primary.appendChild(document.createTextNode(widget.primary_text || "--"));
      panel.appendChild(primary);
    }

    if (widget.secondary_text) {
      secondary = document.createElement("div");
      secondary.className = "muted";
      secondary.appendChild(document.createTextNode(widget.secondary_text));
      panel.appendChild(secondary);
    }

    if (widget.history && widget.history.points && widget.history.points.length > 1) {
      historyContainer = buildSensorHistory(widget.history);
      if (historyContainer) {
        panel.appendChild(historyContainer);
      }
    }

    if (widget.rows && widget.rows.length) {
      rowContainer = document.createElement("div");
      for (i = 0; i < widget.rows.length; i += 1) {
        rowContainer.appendChild(buildRow(widget.rows[i]));
      }
      panel.appendChild(rowContainer);
    }

    if (widget.forecast && widget.forecast.length) {
      forecastContainer = buildForecast(widget.forecast_title, widget.forecast);
      panel.appendChild(forecastContainer);
    }

    if (widget.actions && widget.actions.length) {
      actionsContainer = document.createElement("div");
      actionsContainer.className = "controls";
      actionsContainer.appendChild(buildActionRow(widget.actions));
      panel.appendChild(actionsContainer);
    }

    return panel;
  }

  function buildRow(rowData) {
    var row = document.createElement("div");
    var label = document.createElement("div");
    var value = document.createElement("div");

    row.className = "row";
    label.className = "label";
    value.className = "value" + (!rowData.available ? " value-muted" : "");

    label.appendChild(document.createTextNode(rowData.label));
    value.appendChild(document.createTextNode(rowData.value || "--"));

    row.appendChild(label);
    row.appendChild(value);
    return row;
  }

  function buildActionRow(actions) {
    var container = document.createElement("div");
    var i;

    container.className = "button-row";

    for (i = 0; i < actions.length; i += 1) {
      container.appendChild(buildActionButton(actions[i]));
    }

    return container;
  }

  function buildForecast(title, items) {
    var container = document.createElement("div");
    var heading;
    var grid = document.createElement("div");
    var i;

    container.className = "weather-forecast";

    if (title) {
      heading = document.createElement("div");
      heading.className = "section-label";
      heading.appendChild(document.createTextNode(title));
      container.appendChild(heading);
    }

    grid.className = "forecast-grid";
    for (i = 0; i < items.length; i += 1) {
      grid.appendChild(buildForecastCard(items[i]));
    }

    container.appendChild(grid);
    return container;
  }

  function buildSensorHistory(history) {
    var container;
    var heading;
    var stats;
    var labels;
    var startLabel;
    var endLabel;

    if (!history || !history.points || history.points.length < 2) {
      return null;
    }

    container = document.createElement("div");
    container.className = "sensor-history";

    if (history.title) {
      heading = document.createElement("div");
      heading.className = "section-label";
      heading.appendChild(document.createTextNode(history.title));
      container.appendChild(heading);
    }

    container.appendChild(buildSensorHistoryChart(history));

    if (history.min_label || history.max_label) {
      stats = document.createElement("div");
      stats.className = "sensor-history-stats";

      if (history.min_label) {
        stats.appendChild(buildSensorHistoryStat("Min", history.min_label));
      }

      if (history.max_label) {
        stats.appendChild(buildSensorHistoryStat("Max", history.max_label));
      }

      container.appendChild(stats);
    }

    if (history.start_label || history.end_label) {
      labels = document.createElement("div");
      labels.className = "sensor-history-labels";

      startLabel = document.createElement("div");
      startLabel.appendChild(document.createTextNode(history.start_label || "--"));
      labels.appendChild(startLabel);

      endLabel = document.createElement("div");
      endLabel.appendChild(document.createTextNode(history.end_label || "--"));
      labels.appendChild(endLabel);

      container.appendChild(labels);
    }

    return container;
  }

  function buildSensorHistoryStat(label, value) {
    var item = document.createElement("div");
    var labelNode = document.createElement("span");
    var valueNode = document.createElement("span");

    item.className = "sensor-history-stat";

    labelNode.className = "sensor-history-stat-label";
    labelNode.appendChild(document.createTextNode(label));
    item.appendChild(labelNode);

    valueNode.className = "sensor-history-stat-value";
    valueNode.appendChild(document.createTextNode(value));
    item.appendChild(valueNode);

    return item;
  }

  function buildSensorHistoryChart(history) {
    var SVG_NS = "http://www.w3.org/2000/svg";
    var chart = document.createElement("div");
    var svg = document.createElementNS(SVG_NS, "svg");
    var points = (history && history.points) || [];
    var tone = "default";
    var width = 100;
    var height = 44;
    var padding = 3;
    var contentWidth = width - padding * 2;
    var contentHeight = height - padding * 2;
    var values = [];
    var minValue = null;
    var maxValue = null;
    var i;
    var value;
    var range;
    var pointCount;
    var linePath = "";
    var areaPath = "";
    var x;
    var y;
    var normalized;
    var guide;
    var line;
    var area;

    if (history && history.tone === "alert") {
      tone = "alert";
    } else if (history && history.tone === "warning") {
      tone = "warning";
    }

    chart.className =
      "sensor-history-chart" +
      (tone === "alert" ? " sensor-history-chart-alert" : "") +
      (tone === "warning" ? " sensor-history-chart-warning" : "");

    for (i = 0; i < points.length; i += 1) {
      value = parseFloat(points[i].value);
      if (isNaN(value)) {
        continue;
      }
      values.push(value);
      if (minValue === null || value < minValue) {
        minValue = value;
      }
      if (maxValue === null || value > maxValue) {
        maxValue = value;
      }
    }

    if (values.length < 2 || minValue === null || maxValue === null) {
      return chart;
    }

    range = maxValue - minValue;
    pointCount = values.length;

    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");

    for (i = 1; i <= 3; i += 1) {
      guide = document.createElementNS(SVG_NS, "line");
      y = padding + contentHeight * (i / 4);
      guide.setAttribute("x1", padding);
      guide.setAttribute("y1", y);
      guide.setAttribute("x2", width - padding);
      guide.setAttribute("y2", y);
      guide.setAttribute("class", "sensor-history-guide");
      svg.appendChild(guide);
    }

    for (i = 0; i < pointCount; i += 1) {
      x = padding + (contentWidth * i) / (pointCount - 1);
      normalized = range === 0 ? 0.5 : (values[i] - minValue) / range;
      y = height - padding - normalized * contentHeight;

      if (i === 0) {
        linePath = "M " + x.toFixed(2) + " " + y.toFixed(2);
        areaPath = linePath;
      } else {
        linePath += " L " + x.toFixed(2) + " " + y.toFixed(2);
        areaPath += " L " + x.toFixed(2) + " " + y.toFixed(2);
      }
    }

    areaPath +=
      " L " +
      (width - padding).toFixed(2) +
      " " +
      (height - padding).toFixed(2) +
      " L " +
      padding.toFixed(2) +
      " " +
      (height - padding).toFixed(2) +
      " Z";

    area = document.createElementNS(SVG_NS, "path");
    area.setAttribute("d", areaPath);
    area.setAttribute(
      "class",
      "sensor-history-area" +
        (tone === "alert" ? " sensor-history-area-alert" : "") +
        (tone === "warning" ? " sensor-history-area-warning" : "")
    );
    svg.appendChild(area);

    line = document.createElementNS(SVG_NS, "path");
    line.setAttribute("d", linePath);
    line.setAttribute(
      "class",
      "sensor-history-line" +
        (tone === "alert" ? " sensor-history-line-alert" : "") +
        (tone === "warning" ? " sensor-history-line-warning" : "")
    );
    svg.appendChild(line);

    chart.appendChild(svg);
    return chart;
  }

  function buildForecastCard(item) {
    var card = document.createElement("div");
    var time = document.createElement("div");
    var primary = document.createElement("div");
    var secondary;

    card.className = "forecast-card" + (!item.available ? " forecast-card-muted" : "");

    time.className = "forecast-time";
    time.appendChild(document.createTextNode(item.time || "--"));
    card.appendChild(time);

    primary.className = "forecast-primary";
    primary.appendChild(document.createTextNode(item.primary_text || "--"));
    card.appendChild(primary);

    if (item.secondary_text) {
      secondary = document.createElement("div");
      secondary.className = "forecast-secondary";
      secondary.appendChild(document.createTextNode(item.secondary_text));
      card.appendChild(secondary);
    }

    return card;
  }

  function buildActionButton(action) {
    var button = document.createElement("button");

    button.type = "button";
    button.disabled = !!action.disabled;
    button.className = resolveActionClass(action);
    button.appendChild(document.createTextNode(action.label));

    if (!action.disabled) {
      attachActionHandler(button, action);
    }

    return button;
  }

  function resolveActionClass(action) {
    if (action.active) {
      return "mode-active";
    }
    if (action.variant === "primary") {
      return "primary";
    }
    if (action.variant === "success") {
      return "mode-active";
    }
    return "";
  }

  function attachActionHandler(button, action) {
    button.onclick = function () {
      if (action.action === "scene") {
        sendAction(
          "POST",
          "/api/actions/scene/" + encodeURIComponent(action.scene_id),
          null,
          "Scene " + humanize(action.scene_id) + " triggered."
        );
        return;
      }

      if (action.action === "heater_toggle") {
        sendAction(
          "POST",
          "/api/actions/heater/toggle",
          { widget_id: action.widget_id },
          "Heater updated."
        );
        return;
      }

      if (action.action === "heater_mode") {
        sendAction(
          "POST",
          "/api/actions/heater/mode",
          { widget_id: action.widget_id, mode: action.mode },
          "Mode changed to " + humanize(action.mode) + "."
        );
      }
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
      renderDashboard(dashboardData);
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

  function saveActivePageId(pageId) {
    if (!pageId) {
      return;
    }
    try {
      window.localStorage.setItem(ACTIVE_PAGE_STORAGE_KEY, pageId);
    } catch (error) {
      return;
    }
  }

  function loadSavedPageId() {
    try {
      return window.localStorage.getItem(ACTIVE_PAGE_STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function boot() {
    ensurePageLayout();
    syncDashboardViewport();
    formatClock();
    bindPageSwipeHandlers();
    scheduleDashboardFit();
    window.addEventListener("resize", scheduleDashboardFit, false);
    window.addEventListener("orientationchange", scheduleDashboardFit, false);
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", scheduleDashboardFit, false);
      window.visualViewport.addEventListener("scroll", scheduleDashboardFit, false);
    }
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
