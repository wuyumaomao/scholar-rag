const API_BASE = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);

  if (response.status === 204) {
    return null;
  }

  let body;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw new Error(body?.detail || `Request failed (${response.status})`);
  }

  return body;
}

export function getFiles() {
  return request("/files");
}

export function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);

  return request("/files/upload", {
    method: "POST",
    body: form,
  });
}

export function sendChat({ file_id, query, session_id = null }) {
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_id, query, session_id }),
  });
}

function parseSseFrame(frame) {
  let event = "message";
  const data = [];

  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value;
    if (field === "data") data.push(value);
  }

  return { event, data: data.join("\n") };
}

export async function streamChat({
  file_id,
  query,
  session_id = null,
  onToken,
}) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ file_id, query, session_id }),
  });

  if (!response.ok) {
    let body;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new Error(body?.detail || `Request failed (${response.status})`);
  }
  if (!response.body) throw new Error("浏览器无法读取流式响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let sessionId = null;
  let completed = false;

  const dispatch = (frame) => {
    if (!frame.trim()) return;
    const { event, data } = parseSseFrame(frame);
    if (!["token", "done", "error"].includes(event)) return;
    if (!data) return;

    let payload;
    try {
      payload = JSON.parse(data);
    } catch {
      throw new Error("流式响应格式无效");
    }

    if (event === "token") {
      if (typeof payload.text === "string") onToken?.(payload.text);
    } else if (event === "done") {
      if (typeof payload.session_id !== "string" || !payload.session_id) {
        throw new Error("流式响应缺少会话编号");
      }
      sessionId = payload.session_id;
      completed = true;
    } else if (event === "error") {
      throw new Error(payload.detail || "流式回答失败");
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let boundary;
      while ((boundary = buffer.match(/\r?\n\r?\n/))) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        dispatch(frame);
      }

      if (done) {
        break;
      }
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }

  if (!completed) throw new Error("流式回答提前结束");
  return { session_id: sessionId };
}

export function getSessions() {
  return request("/sessions");
}

export function getHistory(sessionId) {
  return request(`/sessions/${encodeURIComponent(sessionId)}/history`);
}

export function deleteSession(sessionId) {
  return request(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}
