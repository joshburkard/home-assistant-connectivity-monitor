console.log("[CM] script start");

var CM_DEVICE_TYPES = ["Bluetooth", "ESP32", "Matter", "Network", "WebPage", "ZigBee"];
var CM_STATUS_OPTIONS = {
  Bluetooth: ["Active", "Inactive", "All"],
  ESP32:    ["Active", "Inactive", "All"],
  Matter:   ["Active", "Inactive", "All"],
  ZigBee:   ["Active", "Inactive", "All"],
  WebPage:  ["Connected", "Disconnected", "All"],
  Network:  ["Connected", "Disconnected", "Partially Connected",
             "Disconnected & Partially Connected",
             "Connected & Partially Connected", "All"]
};
var CM_DEFAULT_STATUS = { Bluetooth: "All", ESP32: "All", Matter: "All", ZigBee: "All", Network: "All", WebPage: "All" };
var CM_ENTITY_STATUS_OPTIONS = [
  "Connected", "Disconnected", "Partially Connected",
  "Disconnected & Partially Connected",
  "Connected & Partially Connected",
  "Active", "Inactive", "All"
];

var CM_STATUS_META = {
  Connected:             { label: "Connected",            css: "ok",      icon: "\u2713" },
  Disconnected:          { label: "Disconnected",         css: "error",   icon: "\u2717" },
  "Not Connected":       { label: "Not Connected",        css: "error",   icon: "\u2717" },
  "Partially Connected": { label: "Partially Connected",  css: "warning", icon: "\u26a0" },
  Active:                { label: "Active",               css: "ok",      icon: "\u2713" },
  Inactive:              { label: "Inactive",             css: "error",   icon: "\u2717" },
  Unknown:               { label: "Unknown",              css: "unknown", icon: "?" }
};

var CM_STATUS_ORDER = {
  Disconnected: 0, "Not Connected": 0, Inactive: 0,
  "Partially Connected": 2,
  Connected: 3, Active: 3, Unknown: 99
};

function cmEsc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, function(c) {
    return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];
  });
}

function cmNormalizeEntityList(value) {
  var raw = [];
  if (Array.isArray(value)) raw = value;
  else if (typeof value === "string") raw = value.split(/[\n,]/);
  var out = [];
  for (var i = 0; i < raw.length; i++) {
    var v = String(raw[i] || "").trim();
    if (!v) continue;
    out.push(v);
  }
  return out;
}

function cmMonitorKindForState(entityId, stateObj) {
  if (!stateObj) return null;
  var attrs = stateObj.attributes || {};
  var mt = attrs.monitor_type;
  if (mt === "webpage") return "WebPage";
  if (!mt && attrs.url && cmWebPageCheckForState(stateObj)) return "WebPage";
  if (!mt && entityId.endsWith("_overall")) return "Network";
  if (mt === "zha") return "ZigBee";
  if (mt === "matter") return "Matter";
  if (mt === "bluetooth") return "Bluetooth";
  if (mt === "esphome") return "ESP32";
  if (!mt) return "Network";
  return null;
}

function cmIsWebPageOverall(stateObj) {
  return cmWebPageCheckForState(stateObj) === "overall";
}

var CM_WEBPAGE_CHECK_LABELS = {
  dns: "DNS Status",
  http: "WebPage Reachable",
  certificate: "Certificate Status",
  content: "Content Status",
  response_time: "Response Time",
  certificate_days: "Certificate Days Remaining"
};

function cmWebPageCheckForState(stateObj) {
  var attrs = stateObj.attributes || {};
  if (attrs.webpage_check) return attrs.webpage_check;
  if (attrs.monitor_type && attrs.monitor_type !== "webpage") return null;
  if (!attrs.url) return null;
  if ((attrs.monitor_type === "webpage" &&
       Object.prototype.hasOwnProperty.call(attrs, "connected")) ||
      Object.prototype.hasOwnProperty.call(attrs, "text_check_enabled") ||
      Object.prototype.hasOwnProperty.call(attrs, "certificate_warning_days")) {
    return "overall";
  }
  var name = attrs.friendly_name || "";
  if (/ (?:Overall|WebPage) Status$/.test(name)) return "overall";
  for (var check in CM_WEBPAGE_CHECK_LABELS) {
    var label = CM_WEBPAGE_CHECK_LABELS[check];
    if ((attrs.monitor_type === "webpage" && name === label) ||
        name.endsWith(" " + label)) return check;
  }
  return null;
}

function cmWebPageDeviceName(stateObj) {
  var attrs = stateObj.attributes || {};
  if (attrs.device_name) return attrs.device_name;
  var name = (attrs.friendly_name || "").replace(/ (?:Overall|WebPage) Status$/, "");
  return name || attrs.url || stateObj.entity_id;
}

function cmGetSelectableDevices(hass) {
  var out = [];
  if (!hass || !hass.states) return out;
  var states = hass.states;
  for (var eid in states) {
    var s = states[eid];
    if (!s || !s.attributes) continue;
    var kind = cmMonitorKindForState(eid, s);
    if (kind !== "WebPage" && !eid.startsWith("sensor.connectivity_monitor_")) continue;
    if (!kind) continue;

    if (kind === "WebPage") {
      if (!cmIsWebPageOverall(s)) continue;
    } else if (kind === "Network") {
      if (!eid.endsWith("_overall")) continue;
    } else {
      if (eid.endsWith("_overall") || eid.endsWith("_ad")) continue;
    }

    var attrs = s.attributes;
    var subtitle = attrs.url || attrs.host || attrs.ieee || attrs.node_id || attrs.bt_address || attrs.device_id || "";
    var name = kind === "WebPage" ? cmWebPageDeviceName(s) :
      (attrs.device_name || attrs.friendly_name || subtitle || eid);
    out.push({
      entityId: eid,
      name: name,
      kind: kind,
      subtitle: subtitle
    });
  }

  out.sort(function(a, b) {
    return a.name.localeCompare(b.name) || a.entityId.localeCompare(b.entityId);
  });
  return out;
}

// --- Visual editor ---
class ConnectivityMonitorCardEditor extends HTMLElement {
  setConfig(config) {
    var oldConfig = this._config;
    this._config = Object.assign({}, config);
    // Skip full re-render if an input field has focus (prevents losing cursor position)
    if (oldConfig && this.shadowRoot) {
      var active = this.shadowRoot.activeElement;
      if (active && (active.id === "cm_title" || active.id === "cm_icon")) return;
    }
    this._render();
  }
  set hass(hass) { this._hass = hass; }
  connectedCallback() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }
  _render() {
    if (!this.shadowRoot) return;
    if (!this._config) return;
    var dt = this._config.device_type || "Network";
    var selectedDevices = cmNormalizeEntityList(this._config.device_list || this._config.entities);
    var mode = this._config.selection_mode || (selectedDevices.length > 0 ? "device_list" : "device_type");
    var sf = this._config.status_filter || CM_DEFAULT_STATUS[dt] || "All";
    var title = this._config.title != null ? this._config.title : "";
    var opts = mode === "device_list" ? CM_ENTITY_STATUS_OPTIONS : (CM_STATUS_OPTIONS[dt] || CM_STATUS_OPTIONS["Network"]);
    var allSelectable = cmGetSelectableDevices(this._hass);

    var icon = this._config.icon != null ? this._config.icon : "";

    var dtOptions = "";
    for (var i = 0; i < CM_DEVICE_TYPES.length; i++) {
      var t = CM_DEVICE_TYPES[i];
      dtOptions += "<option value='" + t + "'" + (t === dt ? " selected" : "") + ">" + t + "</option>";
    }
    var sfOptions = "";
    for (var j = 0; j < opts.length; j++) {
      var s = opts[j];
      sfOptions += "<option value='" + s + "'" + (s === sf ? " selected" : "") + ">" + s + "</option>";
    }
    var deviceOptions = "";
    for (var k = 0; k < allSelectable.length; k++) {
      var dev = allSelectable[k];
      var selected = selectedDevices.indexOf(dev.entityId) >= 0;
      var text = dev.name + " [" + dev.kind + "]" + (dev.subtitle ? " - " + dev.subtitle : "");
      deviceOptions += "<option value='" + cmEsc(dev.entityId) + "'" + (selected ? " selected" : "") + ">" + cmEsc(text) + "</option>";
    }

    this.shadowRoot.innerHTML =
      "<style>" +
      ".form { display:flex; flex-direction:column; gap:16px; padding:16px; }" +
      "label { font-size:14px; font-weight:500; color:var(--primary-text-color); display:block; margin-bottom:4px; }" +
      "select, input[type=text], textarea { width:100%; padding:8px 12px; border:1px solid var(--divider-color,#e0e0e0); border-radius:4px; background:var(--card-background-color,#fff); color:var(--primary-text-color); font-size:14px; }" +
      "select:focus, input[type=text]:focus, textarea:focus { outline:none; border-color:var(--primary-color); }" +
      "select[multiple] { min-height:150px; }" +
      ".field-help { color:var(--secondary-text-color); font-size:12px; margin-top:4px; }" +
      "ha-icon-picker { display:block; width:100%; }" +
      "</style>" +
      "<div class='form'>" +
      "<div><label>Icon</label>" +
      "<ha-icon-picker id='cm_icon' value='" + cmEsc(icon) + "' placeholder='mdi:lan'></ha-icon-picker></div>" +
      "<div><label>Title</label>" +
      "<input type='text' id='cm_title' value='" + cmEsc(title) + "' placeholder='Connectivity Monitor - " + cmEsc(dt) + "'></div>" +
      "<div><label>Selection</label>" +
      "<select id='cm_mode'>" +
      "<option value='device_type'" + (mode === "device_type" ? " selected" : "") + ">Device Type</option>" +
      "<option value='device_list'" + (mode === "device_list" ? " selected" : "") + ">Device List</option>" +
      "</select></div>" +
      "<div><label>Device Type</label>" +
      "<select id='cm_dt'>" + dtOptions + "</select></div>" +
      "<div><label>Device List</label>" +
      "<select id='cm_devices' multiple>" + deviceOptions + "</select>" +
      "<div class='field-help'>Only Connectivity Monitor devices are shown.</div></div>" +
      "<div><label>Status Filter</label>" +
      "<select id='cm_sf'>" + sfOptions + "</select></div>" +
      "</div>";

    var dtRow = this.shadowRoot.getElementById("cm_dt").closest("div");
    var entitiesRow = this.shadowRoot.getElementById("cm_devices").closest("div");
    if (dtRow) dtRow.style.display = mode === "device_type" ? "" : "none";
    if (entitiesRow) entitiesRow.style.display = mode === "device_list" ? "" : "none";

    var self = this;
    this.shadowRoot.getElementById("cm_icon").addEventListener("value-changed", function(e) {
      var v = e.detail && e.detail.value != null ? e.detail.value : e.target.value;
      self._config = Object.assign({}, self._config, { icon: v });
      self._fire();
    });
    this.shadowRoot.getElementById("cm_icon").addEventListener("input", function(e) {
      self._config = Object.assign({}, self._config, { icon: e.target.value });
      self._fire();
    });
    this.shadowRoot.getElementById("cm_title").addEventListener("input", function(e) {
      self._config = Object.assign({}, self._config, { title: e.target.value });
      self._fire();
    });
    this.shadowRoot.getElementById("cm_mode").addEventListener("change", function(e) {
      var v = e.target.value;
      self._config = Object.assign({}, self._config, { selection_mode: v, status_filter: "All" });
      self._fire();
      self._render();
    });
    this.shadowRoot.getElementById("cm_dt").addEventListener("change", function(e) {
      var v = e.target.value;
      self._config = Object.assign({}, self._config, { device_type: v, status_filter: CM_DEFAULT_STATUS[v] });
      self._fire();
      self._render();
    });
    this.shadowRoot.getElementById("cm_devices").addEventListener("change", function(e) {
      var selected = [];
      var opts = e.target.options;
      for (var i = 0; i < opts.length; i++) {
        if (opts[i].selected) selected.push(opts[i].value);
      }
      self._config = Object.assign({}, self._config, { device_list: selected, entities: selected });
      self._fire();
    });
    this.shadowRoot.getElementById("cm_sf").addEventListener("change", function(e) {
      var v = e.target.value;
      self._config = Object.assign({}, self._config, { status_filter: v });
      self._fire();
    });
  }
  _fire() {
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: this._config }, bubbles: true, composed: true
    }));
  }
}
customElements.define("connectivity-monitor-card-editor", ConnectivityMonitorCardEditor);
console.log("[CM] editor defined OK");

// --- Card ---
class ConnectivityMonitorCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("connectivity-monitor-card-editor");
  }
  static getStubConfig() { return { device_type: "Network", status_filter: "All" }; }
  setConfig(config) {
    this._config = Object.assign({}, config);
    if (!this._config.selection_mode) {
      this._config.selection_mode = cmNormalizeEntityList(this._config.device_list || this._config.entities).length > 0 ? "device_list" : "device_type";
    }
    if (this._config.selection_mode === "entities") {
      this._config.selection_mode = "device_list";
    }
    if (this._config.selection_mode === "device_list") {
      this._config.device_list = cmNormalizeEntityList(this._config.device_list || this._config.entities);
      this._config.entities = this._config.device_list;
    }
    // Migrate old "Both" value to "All"
    if (this._config && this._config.status_filter === "Both") {
      this._config = Object.assign({}, this._config, { status_filter: "All" });
    }
    if (this.shadowRoot) this._render();
  }
  getCardSize() { return 8; }
  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) return;
    var fp = "";
    for (var eid in hass.states) {
      if (eid.indexOf("sensor.connectivity_monitor_") === 0 ||
          cmMonitorKindForState(eid, hass.states[eid]) === "WebPage") {
        fp += eid + "=" + hass.states[eid].state + "|";
        if (cmMonitorKindForState(eid, hass.states[eid]) === "WebPage") {
          fp += JSON.stringify(hass.states[eid].attributes) + "|";
        }
      }
    }
    if (fp === this._lastFingerprint) return;
    this._lastFingerprint = fp;
    this._render();
  }
  connectedCallback() {
    this.attachShadow({ mode: "open" });
    // Collapsed state: tracked per entity_id. null = not yet initialised.
    if (!this._collapsed) this._collapsed = null;
    if (!this._lastDeviceStatuses) this._lastDeviceStatuses = null;
    // Click handler for navigation + toggle
    var self = this;
    this.shadowRoot.addEventListener("click", function(e) {
      // Toggle chevron
      var toggleBtn = e.target.closest("[data-toggle]");
      if (toggleBtn) {
        e.stopPropagation();
        var key = toggleBtn.getAttribute("data-toggle");
        if (self._collapsed.has(key)) self._collapsed.delete(key);
        else self._collapsed.add(key);
        self._applyCollapse();
        return;
      }
      // Navigate to device page
      var devEl = e.target.closest("[data-device]");
      if (devEl) {
        e.stopPropagation();
        var devId = devEl.getAttribute("data-device");
        window.history.pushState(null, "", "/config/devices/device/" + devId);
        window.dispatchEvent(new CustomEvent("location-changed"));
        return;
      }
      // Navigate to entity page
      var entEl = e.target.closest("[data-entity]");
      if (entEl) {
        e.stopPropagation();
        var entId = entEl.getAttribute("data-entity");
        var evt = new CustomEvent("hass-more-info", { detail: { entityId: entId }, bubbles: true, composed: true });
        self.dispatchEvent(evt);
        return;
      }
    });
    this._render();
  }

  // -- Data fetching --
  _buildDeviceFromState(entityId, s, states) {
    if (!s) return null;
    var attrs = s.attributes || {};
    var monitorType = attrs.monitor_type;

    if (cmMonitorKindForState(entityId, s) === "WebPage") {
      if (!cmIsWebPageOverall(s)) return null;
      var checks = [];
      var checkOrder = Object.keys(CM_WEBPAGE_CHECK_LABELS);
      for (var checkId in states) {
        var checkState = states[checkId];
        var checkAttrs = checkState.attributes || {};
        if (checkId === entityId || checkAttrs.url !== attrs.url) continue;
        if (cmMonitorKindForState(checkId, checkState) !== "WebPage") continue;
        if (cmIsWebPageOverall(checkState)) continue;
        checks.push(checkState);
      }
      checks.sort(function(a, b) {
        return checkOrder.indexOf(cmWebPageCheckForState(a)) -
          checkOrder.indexOf(cmWebPageCheckForState(b)) ||
          a.entity_id.localeCompare(b.entity_id);
      });
      return {
        entityId: entityId,
        name: cmWebPageDeviceName(s),
        subtitle: attrs.url,
        status: s.state || "Unknown",
        sensors: checks,
        kind: "WebPage"
      };
    }

    if (!monitorType && entityId.endsWith("_overall")) monitorType = "network";

    if (monitorType !== "zha" && monitorType !== "matter" && monitorType !== "esphome" && monitorType !== "bluetooth") {
      var host = attrs.host || attrs.device_name || attrs.friendly_name || entityId;
      var sensors = [];
      if (attrs.host) {
        for (var sid in states) {
          var ss = states[sid];
          if (!sid.startsWith("sensor.connectivity_monitor_")) continue;
          if (sid.endsWith("_overall") || sid.endsWith("_ad")) continue;
          if ((ss.attributes || {}).host !== attrs.host) continue;
          var smt = (ss.attributes || {}).monitor_type;
          if (smt === "zha" || smt === "matter" || smt === "esphome" || smt === "bluetooth" ||
              cmMonitorKindForState(sid, ss) === "WebPage") continue;
          sensors.push(ss);
        }
        sensors.sort(function(a, b) {
          var af = (a.state === "Disconnected" || a.state === "Not Connected") ? 0 : 1;
          var bf = (b.state === "Disconnected" || b.state === "Not Connected") ? 0 : 1;
          return af !== bf ? af - bf : a.entity_id.localeCompare(b.entity_id);
        });
      }
      return {
        entityId: entityId,
        name: attrs.device_name || attrs.friendly_name || host,
        subtitle: attrs.host || host,
        status: s.state || "Unknown",
        sensors: sensors,
        kind: "Network"
      };
    }

    var sub = "";
    var kind = "ESP32";
    if (monitorType === "zha") {
      kind = "ZigBee";
      sub = attrs.ieee || "";
    } else if (monitorType === "matter") {
      kind = "Matter";
      sub = attrs.node_id || "";
    } else if (monitorType === "bluetooth") {
      kind = "Bluetooth";
      sub = attrs.bt_address || "";
    } else {
      sub = attrs.device_id || "";
    }
    return {
      entityId: entityId,
      name: attrs.device_name || attrs.friendly_name || sub || entityId,
      subtitle: sub,
      status: s.state || "Unknown",
      sensors: [],
      minutesAgo: attrs.minutes_ago,
      timeout: attrs.timeout_minutes,
      kind: kind
    };
  }

  _getDevices() {
    if (!this._hass) return [];
    var states = this._hass.states;
    var dt = (this._config && this._config.device_type) || "Network";
    var mode = (this._config && this._config.selection_mode) || "device_type";
    var devices = [];

    if (mode === "device_list") {
      var entityIds = cmNormalizeEntityList((this._config && this._config.device_list) || (this._config && this._config.entities));
      for (var i = 0; i < entityIds.length; i++) {
        var selectedId = entityIds[i];
        var selectedState = states[selectedId];
        var selectedDevice = this._buildDeviceFromState(selectedId, selectedState, states);
        if (selectedDevice) devices.push(selectedDevice);
      }
      return devices;
    }

    if (dt === "WebPage") {
      for (var webpageId in states) {
        if (cmMonitorKindForState(webpageId, states[webpageId]) !== "WebPage") continue;
        var webpage = this._buildDeviceFromState(webpageId, states[webpageId], states);
        if (webpage) devices.push(webpage);
      }
      return devices;
    }

    if (dt === "Network") {
      for (var entityId in states) {
        if (!entityId.startsWith("sensor.connectivity_monitor_")) continue;
        if (!entityId.endsWith("_overall")) continue;
        var st = states[entityId];
        if (!st || !st.attributes) continue;
        if (cmMonitorKindForState(entityId, st) === "WebPage") continue;
        if (st.attributes.monitor_type === "zha") continue;
        if (st.attributes.monitor_type === "matter") continue;
        if (st.attributes.monitor_type === "esphome") continue;
        if (st.attributes.monitor_type === "bluetooth") continue;
        var netDevice = this._buildDeviceFromState(entityId, st, states);
        if (netDevice) devices.push(netDevice);
      }
    } else {
      var monitorType = dt === "ZigBee" ? "zha" : dt === "Matter" ? "matter" : dt === "Bluetooth" ? "bluetooth" : "esphome";
      for (var eid in states) {
        if (!eid.startsWith("sensor.connectivity_monitor_")) continue;
        var s = states[eid];
        if (!s || !s.attributes || s.attributes.monitor_type !== monitorType) continue;
        var typedDevice = this._buildDeviceFromState(eid, s, states);
        if (typedDevice) devices.push(typedDevice);
      }
    }
    return devices;
  }

  _filterDevices(devices) {
    var sf = (this._config && this._config.status_filter) || "All";
    if (sf === "All") return devices;
    var result = [];
    for (var i = 0; i < devices.length; i++) {
      var d = devices[i];
      if (sf === "Connected" && d.status === "Connected") result.push(d);
      else if (sf === "Disconnected" && (d.status === "Disconnected" || d.status === "Not Connected")) result.push(d);
      else if (sf === "Partially Connected" && d.status === "Partially Connected") result.push(d);
      else if (sf === "Disconnected & Partially Connected" && (d.status === "Disconnected" || d.status === "Not Connected" || d.status === "Partially Connected")) result.push(d);
      else if (sf === "Connected & Partially Connected" && (d.status === "Connected" || d.status === "Partially Connected")) result.push(d);
      else if (sf === "Active" && d.status === "Active") result.push(d);
      else if (sf === "Inactive" && (d.status === "Inactive" || d.status === "Unknown")) result.push(d);
    }
    return result;
  }

  _groupDevices(devices) {
    var map = {};
    for (var i = 0; i < devices.length; i++) {
      var d = devices[i];
      if (!map[d.status]) map[d.status] = [];
      map[d.status].push(d);
    }
    var groups = [];
    for (var status in map) {
      map[status].sort(function(a, b) { return a.name.localeCompare(b.name); });
      groups.push({ status: status, devices: map[status] });
    }
    groups.sort(function(a, b) {
      var oa = CM_STATUS_ORDER[a.status] != null ? CM_STATUS_ORDER[a.status] : 99;
      var ob = CM_STATUS_ORDER[b.status] != null ? CM_STATUS_ORDER[b.status] : 99;
      return oa - ob;
    });
    return groups;
  }

  // -- Rendering --
  _isCollapsedStatus(status) {
    return status === "Connected" || status === "Active";
  }

  _initCollapsed(devices) {
    if (this._collapsed !== null) return;
    this._collapsed = new Set();
    this._lastDeviceStatuses = {};
    for (var i = 0; i < devices.length; i++) {
      if (this._isCollapsedStatus(devices[i].status)) {
        this._collapsed.add(devices[i].entityId);
      }
      this._lastDeviceStatuses[devices[i].entityId] = devices[i].status;
    }
  }

  _syncCollapsedWithStatus(devices) {
    if (this._collapsed === null || this._lastDeviceStatuses === null) {
      this._initCollapsed(devices);
      return;
    }

    var currentStatuses = {};
    for (var i = 0; i < devices.length; i++) {
      var device = devices[i];
      var entityId = device.entityId;
      var status = device.status;
      var previousStatus = this._lastDeviceStatuses[entityId];

      currentStatuses[entityId] = status;

      if (previousStatus == null) {
        if (this._isCollapsedStatus(status)) this._collapsed.add(entityId);
        else this._collapsed.delete(entityId);
        continue;
      }

      if (previousStatus !== status) {
        if (this._isCollapsedStatus(status)) this._collapsed.add(entityId);
        else this._collapsed.delete(entityId);
      }
    }

    this._lastDeviceStatuses = currentStatuses;
  }

  _applyCollapse() {
    if (!this.shadowRoot || !this._collapsed) return;
    var btns = this.shadowRoot.querySelectorAll("[data-toggle]");
    for (var i = 0; i < btns.length; i++) {
      var btn = btns[i];
      var key = btn.getAttribute("data-toggle");
      var card = btn.closest(".device-card");
      var list = card ? card.querySelector(".sensor-list") : null;
      var collapsed = this._collapsed.has(key);
      btn.innerHTML = collapsed ? "\u25b6" : "\u25bc";
      btn.title = collapsed ? "Expand" : "Collapse";
      if (list) list.style.display = collapsed ? "none" : "";
    }
  }

  _renderSensor(sensor) {
    if (cmMonitorKindForState(sensor.entity_id, sensor) === "WebPage") {
      var attrs = sensor.attributes || {};
      var check = cmWebPageCheckForState(sensor);
      var label = CM_WEBPAGE_CHECK_LABELS[check] || attrs.friendly_name || sensor.entity_id;
      var css = "unknown";
      if (["Failed", "Unreachable", "Invalid", "Error", "Missing"].indexOf(sensor.state) >= 0) css = "error";
      else if (sensor.state === "Expiring Soon") css = "warning";
      else if (["Resolved", "Reachable", "Valid", "Found"].indexOf(sensor.state) >= 0) css = "ok";
      var value = sensor.state;
      if (check === "response_time" || check === "certificate_days") {
        if (value !== "" && value != null && Number.isFinite(Number(value))) {
          value += " " + (attrs.unit_of_measurement || (check === "response_time" ? "ms" : "d"));
          if (check === "certificate_days") {
            css = Number(sensor.state) <= 0 ? "error" : "unknown";
          }
        }
      }
      return "<div class='sensor-row clickable' data-entity='" + cmEsc(sensor.entity_id) + "'>" +
        "<span class='dot dot-" + css + "'></span>" +
        "<span class='sensor-proto'>" + cmEsc(label) + "</span>" +
        "<span class='label-" + css + "'>" + cmEsc(value) + "</span>" +
        "<span class='row-arrow'>\u203a</span></div>";
    }
    var st = sensor.state;
    var isErr = (st === "Disconnected" || st === "Not Connected");
    var isWarn = (st === "Partially Connected");
    var dot = isErr ? "error" : isWarn ? "warning" : "ok";
    var proto = sensor.attributes.protocol || "ICMP";
    var port = sensor.attributes.port;
    var service = sensor.attributes.service;
    var label;
    if (service) label = cmEsc(proto) + " - " + cmEsc(service) + " (" + cmEsc(port) + ")";
    else if (port) label = cmEsc(proto) + ":" + cmEsc(port);
    else label = cmEsc(proto);
    var latency = sensor.attributes.latency_ms != null
      ? "<span class='sensor-latency'>" + cmEsc(sensor.attributes.latency_ms) + " ms</span>" : "";
    return "<div class='sensor-row clickable' data-entity='" + cmEsc(sensor.entity_id) + "'>" +
      "<span class='dot dot-" + dot + "'></span>" +
      "<span class='sensor-proto'>" + label + "</span>" +
      "<span class='label-" + dot + "'>" + cmEsc(st) + "</span>" +
      latency +
      "<span class='row-arrow'>\u203a</span>" +
      "</div>";
  }

  _renderDevice(device) {
    var meta = CM_STATUS_META[device.status] || CM_STATUS_META.Unknown;
    var dt = device.kind || ((this._config && this._config.device_type) || "Network");
    var collapsed = this._collapsed && this._collapsed.has(device.entityId);
    var chevron = collapsed ? "\u25b6" : "\u25bc";

    // Resolve HA device_id for navigation
    var deviceAttr = "data-entity='" + cmEsc(device.entityId) + "'";
    if (this._hass && this._hass.entities) {
      var entry = this._hass.entities[device.entityId];
      if (entry && entry.device_id) {
        deviceAttr = "data-device='" + cmEsc(entry.device_id) + "'";
      }
    }

    var html = "<div class='device-card card-" + meta.css + "'>" +
      "<div class='device-header'>" +
      "<button class='toggle-btn' data-toggle='" + cmEsc(device.entityId) + "' title='" + (collapsed ? "Expand" : "Collapse") + "'>" + chevron + "</button>" +
      "<div class='device-info clickable' " + deviceAttr + ">" +
      "<div class='device-name'>" + cmEsc(device.name) + "</div>" +
      "<div class='device-host'>" + cmEsc(device.subtitle) + "</div></div>" +
      "<span class='badge badge-" + meta.css + "'>" + cmEsc(device.status) + "</span></div>";

    var sensorDisplay = collapsed ? "none" : "";
    if ((dt === "Network" || dt === "WebPage") && device.sensors.length > 0) {
      html += "<div class='sensor-list' style='display:" + sensorDisplay + "'>";
      for (var i = 0; i < device.sensors.length; i++) {
        html += this._renderSensor(device.sensors[i]);
      }
      html += "</div>";
    } else if (dt === "ZigBee" && device.minutesAgo != null) {
      var ago;
      if (device.minutesAgo < 60) ago = device.minutesAgo + " min ago";
      else if (device.minutesAgo < 1440) ago = Math.round(device.minutesAgo / 60) + " hr ago";
      else ago = Math.round(device.minutesAgo / 1440) + " day(s) ago";
      html += "<div class='sensor-list' style='display:" + sensorDisplay + "'>" +
        "<div class='sensor-row clickable' data-entity='" + cmEsc(device.entityId) + "'>" +
        "<span class='dot dot-" + meta.css + "'></span>" +
        "<span class='sensor-proto'>Last seen: " + cmEsc(ago) + "</span>" +
        "<span class='row-arrow'>\u203a</span>" +
        "</div></div>";
    } else if ((dt === "Matter" || dt === "ESP32") && device.entityId) {
      html += "<div class='sensor-list' style='display:" + sensorDisplay + "'>" +
        "<div class='sensor-row clickable' data-entity='" + cmEsc(device.entityId) + "'>" +
        "<span class='dot dot-" + meta.css + "'></span>" +
        "<span class='sensor-proto'>" + cmEsc(dt) + " Status</span>" +
        "<span class='label-" + meta.css + "'>" + cmEsc(device.status) + "</span>" +
        "<span class='row-arrow'>\u203a</span>" +
        "</div></div>";
    }
    html += "</div>";
    return html;
  }

  _styles() {
    return "<style>" +
      "*, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }" +
      ".card-header { display:flex; align-items:center; gap:8px; padding:16px 16px 0 16px; font-size:1.4rem; font-weight:500; color:var(--ha-card-header-color,var(--primary-text-color)); }" +
      ".header-icon { --mdc-icon-size:28px; flex-shrink:0; color:var(--primary-text-color); }" +
      ".card-content { padding:16px; }" +
      ".group { margin-bottom:16px; }" +
      ".group-header { display:flex; align-items:center; gap:8px; padding:6px 12px; border-radius:6px 6px 0 0; font-size:0.82rem; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }" +
      ".group-header-error   { background:rgba(244,67,54,.15);  color:var(--error-color,#f44336); }" +
      ".group-header-warning { background:rgba(255,152,0,.15);  color:var(--warning-color,#ff9800); }" +
      ".group-header-ok      { background:rgba(76,175,80,.12);  color:var(--success-color,#4caf50); }" +
      ".group-header-unknown { background:rgba(128,128,128,.12);color:var(--secondary-text-color); }" +
      ".group-count { background:rgba(0,0,0,.12); border-radius:10px; padding:1px 8px; font-size:0.78rem; }" +
      ".device-card { background:var(--card-background-color,#fff); margin-bottom:4px; border-left:4px solid transparent; box-shadow:var(--ha-card-box-shadow,0 1px 4px rgba(0,0,0,.08)); overflow:hidden; }" +
      ".device-card:last-child { margin-bottom:0; border-radius:0 0 6px 6px; }" +
      ".card-error   { border-left-color:var(--error-color,#f44336); }" +
      ".card-warning { border-left-color:var(--warning-color,#ff9800); }" +
      ".card-ok      { border-left-color:var(--success-color,#4caf50); }" +
      ".card-unknown { border-left-color:var(--secondary-text-color); }" +
      ".device-header { display:flex; align-items:center; gap:8px; padding:8px 14px; background:var(--secondary-background-color,rgba(0,0,0,.03)); border-bottom:1px solid var(--divider-color,rgba(0,0,0,.08)); }" +
      ".device-info { flex:1; min-width:0; }" +
      ".device-name { font-size:0.92rem; font-weight:500; }" +
      ".device-host { font-size:0.75rem; color:var(--secondary-text-color); margin-top:1px; }" +
      ".badge { border-radius:20px; padding:2px 10px; font-size:0.73rem; font-weight:600; white-space:nowrap; color:#fff; }" +
      ".badge-error   { background:var(--error-color,#f44336); }" +
      ".badge-warning { background:var(--warning-color,#ff9800); }" +
      ".badge-ok      { background:var(--success-color,#4caf50); }" +
      ".badge-unknown { background:var(--secondary-text-color); }" +
      ".sensor-list { padding:2px 0; }" +
      ".sensor-row { display:flex; align-items:center; padding:5px 14px; gap:10px; border-bottom:1px solid var(--divider-color,rgba(0,0,0,.06)); font-size:0.85rem; }" +
      ".sensor-row:last-child { border-bottom:none; }" +
      ".clickable { cursor:pointer; }" +
      ".clickable:hover { background:var(--secondary-background-color,rgba(0,0,0,.04)); }" +
      ".toggle-btn { background:none; border:none; cursor:pointer; color:var(--secondary-text-color); font-size:0.7rem; padding:2px 4px; flex-shrink:0; line-height:1; border-radius:3px; }" +
      ".toggle-btn:hover { background:var(--secondary-background-color,rgba(0,0,0,.08)); }" +
      ".row-arrow { color:var(--secondary-text-color); font-size:1.1rem; flex-shrink:0; }" +
      ".device-info:hover .device-name { text-decoration:underline; }" +
      ".dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }" +
      ".dot-error   { background:var(--error-color,#f44336); }" +
      ".dot-warning { background:var(--warning-color,#ff9800); }" +
      ".dot-ok      { background:var(--success-color,#4caf50); }" +
      ".dot-unknown { background:var(--secondary-text-color); }" +
      ".sensor-proto { flex:1; color:var(--secondary-text-color); }" +
      ".sensor-latency { font-size:0.78rem; color:var(--secondary-text-color); margin-left:8px; }" +
      ".label-error   { color:var(--error-color,#f44336); font-weight:500; }" +
      ".label-warning { color:var(--warning-color,#ff9800); font-weight:500; }" +
      ".label-ok      { color:var(--success-color,#4caf50); font-weight:500; }" +
      ".label-unknown { color:var(--secondary-text-color); }" +
      ".no-devices { text-align:center; padding:32px 16px; color:var(--secondary-text-color); font-size:0.9rem; }" +
      "</style>";
  }

  _render() {
    if (!this.shadowRoot) return;
    var dt = (this._config && this._config.device_type) || "Network";
    var mode = (this._config && this._config.selection_mode) || "device_type";
    var sf = (this._config && this._config.status_filter) || CM_DEFAULT_STATUS[dt] || "All";
    var allDevices = this._getDevices();
    this._syncCollapsedWithStatus(allDevices);
    var filtered = this._filterDevices(allDevices);
    var groups = this._groupDevices(filtered);

    var bodyHtml = "";
    if (filtered.length === 0) {
      var label = mode === "device_list" ? "selected devices" : (cmEsc(dt) + " devices");
      bodyHtml = "<div class='no-devices'>No " + label +
        (sf !== "All" && sf !== "Both" ? " with status '" + cmEsc(sf) + "'" : "") +
        " found.</div>";
    } else {
      for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var meta = CM_STATUS_META[group.status] || CM_STATUS_META.Unknown;
        bodyHtml += "<div class='group'>" +
          "<div class='group-header group-header-" + meta.css + "'>" +
          "<span>" + meta.icon + "</span>" +
          "<span style='flex:1'>" + cmEsc(meta.label) + "</span>" +
          "<span class='group-count'>" + group.devices.length + "</span></div>";
        for (var d = 0; d < group.devices.length; d++) {
          bodyHtml += this._renderDevice(group.devices[d]);
        }
        bodyHtml += "</div>";
      }
    }

    var title = this._config && this._config.title ? this._config.title : "Connectivity Monitor - " + dt;
    var iconName = this._config && this._config.icon ? this._config.icon : "";
    var headerIcon = iconName ? "<ha-icon icon='" + cmEsc(iconName) + "' class='header-icon'></ha-icon>" : "";

    this.shadowRoot.innerHTML = this._styles() +
      "<ha-card>" +
      "<div class='card-header'>" + headerIcon + "<span>" + cmEsc(title) + "</span></div>" +
      "<div class='card-content'>" + bodyHtml + "</div>" +
      "</ha-card>";
  }
}

customElements.define("connectivity-monitor-card", ConnectivityMonitorCard);
console.log("[CM] element defined OK");

window.customCards = window.customCards || [];
window.customCards.push({
  type: "connectivity-monitor-card",
  name: "Connectivity Monitor",
  description: "Connectivity Monitor card",
});
