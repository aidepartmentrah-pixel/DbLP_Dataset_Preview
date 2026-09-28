import { useEffect, useState } from "react";

export type ApiState<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "empty" }
  | { status: "ready"; data: T };

/** Fetches a dashboard JSON endpoint with loading/empty/error states, per
 * §9.3: "Every chart has an empty state and a loading skeleton." */
export function useApi<T>(path: string, isEmpty: (data: T) => boolean = () => false): ApiState<T> {
  const [state, setState] = useState<ApiState<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetch(path)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
      })
      .then((data: T) => {
        if (cancelled) return;
        setState(isEmpty(data) ? { status: "empty" } : { status: "ready", data });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ status: "error", error: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return state;
}
