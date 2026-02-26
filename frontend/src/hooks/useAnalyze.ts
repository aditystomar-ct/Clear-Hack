import { useCallback, useRef, useState } from "react";
import type { SSEEvent, SSEComplete } from "@/types";

interface AnalyzeState {
  running: boolean;
  progress: number;
  message: string;
  logs: string[];
  result: SSEComplete["data"] | null;
  error: string | null;
}

const initial: AnalyzeState = {
  running: false,
  progress: 0,
  message: "",
  logs: [],
  result: null,
  error: null,
};

export function useAnalyze() {
  const [state, setState] = useState<AnalyzeState>(initial);
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async (formData: FormData) => {
    setState({ ...initial, running: true, message: "Starting analysis..." });
    abortRef.current = new AbortController();

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        setState((s) => ({ ...s, running: false, error: `Server error: ${text}` }));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        setState((s) => ({ ...s, running: false, error: "No response body" }));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6).trim();
          if (!json) continue;

          try {
            const event: SSEEvent = JSON.parse(json);
            if (event.type === "progress") {
              const pct = event.total > 0 ? Math.min(event.step / event.total, 1) : 0;
              setState((s) => ({
                ...s,
                progress: pct,
                message: event.message,
                logs: [...s.logs, event.message].slice(-15),
              }));
            } else if (event.type === "complete") {
              setState((s) => ({
                ...s,
                running: false,
                progress: 1,
                message: "Analysis complete!",
                result: event.data,
              }));
            } else if (event.type === "error") {
              setState((s) => ({
                ...s,
                running: false,
                error: event.message,
              }));
            }
          } catch {
            // ignore parse errors
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setState((s) => ({ ...s, running: false, error: String(err) }));
      }
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(initial);
  }, []);

  return { ...state, start, reset };
}
