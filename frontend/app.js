"use strict";
const byId = (id) => document.getElementById(id);
const logBody = byId("log");
const entries = [];

async function loadStats() {
  try {
    const response = await fetch("/api/stats", { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!response.ok) throw new Error("API returned " + response.status);
    const stats = await response.json();
    byId("strategy").textContent = stats.strategy;
    byId("limit").textContent = String(stats.rate_limit);
    byId("window").textContent = stats.window_seconds + " seconds";
    byId("storage").textContent = stats.storage;
    byId("status").textContent = "API online";
  } catch (error) {
    byId("status").textContent = "API unavailable";
    byId("message").textContent = "Could not load API stats. Check that the backend is running.";
  }
}

function renderLog() {
  logBody.replaceChildren();
  if (entries.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "muted";
    cell.textContent = "No requests yet.";
    row.append(cell);
    logBody.append(row);
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("tr");
    for (const value of [entry.time, entry.client, String(entry.status), entry.remaining, entry.retry]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (value === "200") cell.className = "ok";
      if (value === "429" || value === "503") cell.className = "blocked";
      row.append(cell);
    }
    logBody.append(row);
  }
}

async function sendRequest() {
  const key = byId("api-key").value.trim();
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(key)) {
    byId("message").textContent = "Use 1–128 letters, numbers, underscores, or hyphens for the demo key.";
    return;
  }
  const response = await fetch("/api/data", {
    headers: { "X-API-Key": key, Accept: "application/json" },
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  entries.unshift({ time: new Date().toLocaleTimeString(), client: key, status: response.status,
    remaining: response.headers.get("X-RateLimit-Remaining") ?? "—",
    retry: response.headers.get("Retry-After") ?? "—" });
  entries.splice(12);
  renderLog();
  byId("message").textContent = response.status === 429
    ? "Quota exceeded. Retry after " + (response.headers.get("Retry-After") ?? "a short wait") + " seconds."
    : response.status === 200 ? "Request accepted." : (body.detail ?? "Request failed with status " + response.status);
}

async function runRequests(count) {
  const buttons = document.querySelectorAll("button");
  buttons.forEach((button) => { button.disabled = true; });
  try {
    for (let i = 0; i < count; i += 1) await sendRequest();
  } catch (error) {
    byId("message").textContent = "Request failed. Check the network and backend logs.";
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

byId("request-form").addEventListener("submit", (event) => { event.preventDefault(); void runRequests(1); });
byId("burst").addEventListener("click", () => { void runRequests(5); });
byId("clear").addEventListener("click", () => { entries.length = 0; renderLog(); });
void loadStats();