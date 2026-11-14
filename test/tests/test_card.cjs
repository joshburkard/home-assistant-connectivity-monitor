const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const elements = new Map();
const context = vm.createContext({
  HTMLElement: class {},
  customElements: { define: (name, element) => elements.set(name, element) },
  window: {},
  console: { log() {} },
});
vm.runInContext(
  fs.readFileSync(
    path.join(__dirname, "..", "..", "custom_components", "connectivity_monitor",
      "www", "connectivity_monitor_card.js"),
    "utf8"
  ),
  context
);
const Card = elements.get("connectivity-monitor-card");

function state(entityId, value, attributes) {
  return { entity_id: entityId, state: value, attributes };
}

function webpage(url, prefix, overallStatus = "Disconnected") {
  const states = {};
  const overall = `sensor.${prefix}_overall_status`;
  states[overall] = state(overall, overallStatus, {
    monitor_type: "webpage", webpage_check: "overall", url,
    device_name: "Status <Page>", connected: overallStatus === "Connected",
  });
  const checks = {
    dns: "Resolved", http: "Reachable", certificate: "Expiring Soon",
    content: "Missing", response_time: "42.5", certificate_days: "7",
  };
  for (const [check, value] of Object.entries(checks)) {
    const id = `sensor.${prefix}_${check}`;
    states[id] = state(id, value, {
      monitor_type: "webpage", webpage_check: check, url,
    });
  }
  return { states, overall };
}

function card(states, config = { device_type: "WebPage" }) {
  const result = new Card();
  result.setConfig(config);
  result.hass = { states };
  return result;
}

test("WebPage selection discovers only overall sensors, including renamed entity IDs", () => {
  const first = webpage("https://example.com/status", "renamed");
  const second = webpage("http://example.com/other", "other", "Connected");
  const states = { ...first.states, ...second.states };
  const devices = card(states)._getDevices();
  assert.equal(devices.length, 2);
  assert.equal(devices[0].sensors.length, 6);
  assert.equal(devices[0].subtitle, "https://example.com/status");
  assert.deepEqual(
    Array.from(devices[0].sensors, (sensor) => sensor.attributes.webpage_check),
    ["dns", "http", "certificate", "content", "response_time", "certificate_days"]
  );
  const selectable = context.cmGetSelectableDevices({ states });
  assert.deepEqual(Array.from(selectable, (device) => device.entityId).sort(),
    [first.overall, second.overall].sort());
  assert.ok(Array.from(context.CM_DEVICE_TYPES).includes("WebPage"));
  assert.deepEqual(Array.from(context.CM_STATUS_OPTIONS.WebPage),
    ["Connected", "Disconnected", "All"]);
});

test("WebPage devices stay out of Network cards and work in mixed device lists", () => {
  const page = webpage("https://example.com/", "connectivity_monitor_site");
  const networkId = "sensor.connectivity_monitor_router_overall";
  const states = {
    ...page.states,
    [networkId]: state(networkId, "Connected", { host: "192.0.2.1" }),
  };
  const network = card(states, { device_type: "Network" })._getDevices();
  assert.deepEqual(Array.from(network, (device) => device.entityId), [networkId]);
  const mixed = card(states, {
    selection_mode: "device_list",
    device_list: [networkId, page.overall, "sensor.connectivity_monitor_site_dns"],
    status_filter: "Disconnected",
  });
  assert.deepEqual(Array.from(mixed._getDevices(), (device) => device.kind),
    ["Network", "WebPage"]);
  assert.deepEqual(Array.from(mixed._filterDevices(mixed._getDevices()),
    (device) => device.entityId), [page.overall]);
});

test("unrelated integrations with URL attributes are not discovered as WebPages", () => {
  const id = "sensor.status_page";
  const detail = "sensor.status_page_dns";
  const states = {
    [id]: state(id, "Connected", {
      url: "https://example.com/", connected: true, friendly_name: "Site",
    }),
    [detail]: state(detail, "Resolved", {
      url: "https://example.com/", friendly_name: "DNS Status",
    }),
  };
  assert.equal(card(states)._getDevices().length, 0);
  assert.equal(context.cmGetSelectableDevices({ states }).length, 0);
});

test("WebPage check rows show labels, units, warning/error/unknown colors, and escaped text", () => {
  const page = webpage("https://example.com/?q=<tag>", "site");
  const instance = card(page.states);
  const devices = instance._getDevices();
  const html = instance._renderDevice(devices[0]);
  assert.match(html, /Status &lt;Page&gt;/);
  assert.match(html, /q=&lt;tag&gt;/);
  assert.match(html, /Certificate Status/);
  assert.match(html, /label-warning'>Expiring Soon/);
  assert.match(html, /label-error'>Missing/);
  assert.match(html, /42\.5 ms/);
  assert.match(html, /7 d/);
  assert.doesNotMatch(html, />ICMP</);
  assert.match(html, /data-entity='sensor.site_certificate'/);
  for (const value of ["Unknown", "unknown", "unavailable", "Not Checked"]) {
    const row = instance._renderSensor(state("sensor.site_dns", value, {
      monitor_type: "webpage", webpage_check: "dns", url: "https://example.com/",
    }));
    assert.match(row, /dot-unknown/);
    assert.doesNotMatch(row, /dot-ok/);
  }
});

for (const hasMonitorType of [true, false]) {
test(`WebPage labels and discovery support friendly names with monitor_type=${hasMonitorType}`, () => {
  const page = webpage("https://www.food-bank.net/", "food_bank", "Connected");
  const labels = {
    overall: "Overall Status",
    dns: "DNS Status",
    http: "WebPage Reachable",
    certificate: "Certificate Status",
    content: "Content Status",
    response_time: "Response Time",
    certificate_days: "Certificate Days Remaining",
  };
  for (const entity of Object.values(page.states)) {
    const check = entity.attributes.webpage_check;
    entity.attributes.friendly_name = `Food-Bank.net ${labels[check]}`;
    delete entity.attributes.webpage_check;
    delete entity.attributes.device_name;
    if (!hasMonitorType) delete entity.attributes.monitor_type;
  }
  page.states[page.overall].attributes.text_check_enabled = true;
  page.states[page.overall].attributes.certificate_warning_days = 30;
  const instance = card(page.states);
  const devices = instance._getDevices();
  assert.equal(devices.length, 1);
  assert.equal(devices[0].name, "Food-Bank.net");
  assert.equal(context.cmGetSelectableDevices({ states: page.states })[0].name,
    "Food-Bank.net");
  const html = instance._renderDevice(devices[0]);
  assert.match(html, /class='device-name'>Food-Bank\.net</);
  assert.doesNotMatch(html, /Overall Status|Food-Bank\.net DNS|Food-Bank\.net Certificate/);
  for (const [check, label] of Object.entries(labels)) {
    if (check !== "overall") {
      assert.match(html, new RegExp(`class='sensor-proto'>${label}<`));
    }
  }
  assert.match(html, /42\.5 ms/);
  assert.match(html, /7 d/);
});
}

test("WebPage headers preserve explicit device names and handle URL-based friendly names", () => {
  const page = webpage("https://www.burkard.it/", "burkard", "Connected");
  const overall = page.states[page.overall];
  overall.attributes.device_name = "My Overall Status";
  assert.equal(card(page.states)._getDevices()[0].name, "My Overall Status");
  delete overall.attributes.device_name;
  overall.attributes.friendly_name = "https://www.burkard.it Overall Status";
  assert.equal(card(page.states)._getDevices()[0].name, "https://www.burkard.it");
});

test("existing WebPage overall sensors remain discoverable before a probe result exists", () => {
  const id = "sensor.renamed_webpage";
  const states = {
    [id]: state(id, "Unknown", {
      url: "https://example.com/", text_check_enabled: false,
      certificate_warning_days: 30, friendly_name: "Renamed Page",
    }),
  };
  const devices = card(states)._getDevices();
  assert.equal(devices.length, 1);
  assert.equal(devices[0].status, "Unknown");
  assert.equal(devices[0].name, "Renamed Page");
});

test("HTTP-only webpages render only available checks and preserve network rows", () => {
  const page = webpage("http://example.com/", "http_site", "Connected");
  for (const check of ["certificate", "certificate_days", "content"]) {
    delete page.states[`sensor.http_site_${check}`];
  }
  const instance = card(page.states);
  const devices = instance._getDevices();
  assert.equal(devices[0].sensors.length, 3);
  instance._collapsed = null;
  instance._lastDeviceStatuses = null;
  instance._syncCollapsedWithStatus(devices);
  assert.ok(instance._collapsed.has(page.overall));
  assert.doesNotMatch(instance._renderDevice(devices[0]), /Certificate Status|Content Status/);
  const networkRow = instance._renderSensor(state("sensor.router_tcp", "Disconnected",
    { protocol: "TCP", port: 443, latency_ms: 2 }));
  assert.match(networkRow, /TCP:443/);
  assert.match(networkRow, /dot-error/);
  assert.match(networkRow, /2 ms/);
});

test("WebPage attribute updates trigger rendering even when the status is unchanged", () => {
  const page = webpage("https://example.com/", "renamed_site");
  const instance = card(page.states);
  let renders = 0;
  instance.shadowRoot = {};
  instance._render = () => { renders++; };
  instance.hass = { states: page.states };
  instance.hass = { states: page.states };
  assert.equal(renders, 1);
  const changed = structuredClone(page.states);
  changed["sensor.renamed_site_http"].attributes.http_status = 503;
  instance.hass = { states: changed };
  assert.equal(renders, 2);
});
