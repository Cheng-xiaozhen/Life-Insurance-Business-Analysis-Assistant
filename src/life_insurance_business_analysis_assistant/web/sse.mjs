// FastAPI SSE over POST: preserve UTF-8 and frame boundaries across reads.
export async function consumeEventStream(response, onEvent) {
  if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("报告响应不是事件流");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";
  let data = [];
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let end;
      while ((end = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, end).replace(/\r$/, "");
        buffer = buffer.slice(end + 1);
        if (line === "") {
          if (data.length && onEvent(event, JSON.parse(data.join("\n"))) === true) return;
          event = "message";
          data = [];
        } else if (!line.startsWith(":")) {
          const colon = line.indexOf(":");
          const field = colon < 0 ? line : line.slice(0, colon);
          const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
          if (field === "event") event = value;
          if (field === "data") data.push(value);
        }
      }
      if (done) return;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
