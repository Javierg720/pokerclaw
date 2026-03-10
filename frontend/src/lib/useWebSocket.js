import { useEffect, useRef, useState, useCallback } from 'react';

export function useTableSocket(tableId) {
  const wsRef = useRef(null);
  const [gameState, setGameState] = useState(null);
  const [spectators, setSpectators] = useState(0);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (!tableId) return;

    const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
    const wsUrl = backendUrl.replace('https://', 'wss://').replace('http://', 'ws://');
    const fullUrl = `${wsUrl}/api/ws/table/${tableId}`;

    try {
      const ws = new WebSocket(fullUrl);

      ws.onopen = () => {
        setConnected(true);
        const token = localStorage.getItem('pokerclaw_token');
        if (token) {
          ws.send(JSON.stringify({ type: 'auth', token }));
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'game_state') {
            setGameState(data.game);
          }
          if (data.type === 'spectators') {
            setSpectators(data.count);
          }
        } catch { /* ignore parse errors */ }
      };

      ws.onerror = () => {
        setConnected(false);
      };

      ws.onclose = () => {
        setConnected(false);
        // Auto-reconnect after 3 seconds
        reconnectTimer.current = setTimeout(() => {
          connect();
        }, 3000);
      };

      wsRef.current = ws;
    } catch {
      setConnected(false);
    }
  }, [tableId]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [connect]);

  const send = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { gameState, spectators, connected, send };
}
