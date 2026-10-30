import { useEffect } from "react";

/** Per-route document title, so tabs and history entries say where they lead. */
export function useTitle(title: string | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · FinResearch` : "FinResearch";
  }, [title]);
}
