import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

/** Live updates: any server push invalidates the relevant queries.
 * Reconnects with backoff; queries also poll as a fallback. */
export function useLiveUpdates(): boolean {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const retryRef = useRef(0);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let timer: number | undefined;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${window.location.host}/ws`);
      socket.onopen = () => {
        retryRef.current = 0;
        setConnected(true);
      };
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          queryClient.invalidateQueries({ queryKey: ["stories"] });
          queryClient.invalidateQueries({ queryKey: ["work"] });
          if (msg.story_id) {
            queryClient.invalidateQueries({ queryKey: ["story", msg.story_id] });
            queryClient.invalidateQueries({ queryKey: ["timeline", msg.story_id] });
            queryClient.invalidateQueries({ queryKey: ["artifacts", msg.story_id] });
          }
          if (String(msg.type).startsWith("push.")) {
            queryClient.invalidateQueries({ queryKey: ["push"] });
          }
          queryClient.invalidateQueries({ queryKey: ["audit"] });
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) {
          const delay = Math.min(15000, 1000 * 2 ** retryRef.current++);
          timer = window.setTimeout(connect, delay);
        }
      };
      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      closed = true;
      if (timer) window.clearTimeout(timer);
      socket?.close();
    };
  }, [queryClient]);

  return connected;
}
