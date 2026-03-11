import { useEffect, useRef, useState, useCallback } from 'react';

export function useTableSocket(tableId) {
  const wsRef = useRef(null);
  const [gameState, setGameState] = useState(null);
  const [spectators, setSpectators] = useState(0);
  const [connected, setConnected] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [reactions, setReactions] = useState([]);
  const reconnectTimer = useRef(null);
  const reactionIdRef = useRef(0);

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
          if (data.type === 'game_state' || data.type === 'game_update') {
            setGameState(data.game);
          }
          if (data.type === 'spectators' || data.type === 'spectator_count') {
            setSpectators(data.count);
          }
          if (data.type === 'chat') {
            setChatMessages(prev => [...prev.slice(-49), data]);
          }
          if (data.type === 'chat_history') {
            setChatMessages(data.messages || []);
          }
          if (data.type === 'reaction') {
            const id = ++reactionIdRef.current;
            setReactions(prev => [...prev, { ...data, id }]);
            setTimeout(() => {
              setReactions(prev => prev.filter(r => r.id !== id));
            }, 2000);
          }
        } catch { /* ignore parse errors */ }
      };

      ws.onerror = () => {
        setConnected(false);
      };

      ws.onclose = () => {
        setConnected(false);
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
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  const send = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { gameState, spectators, connected, send, chatMessages, reactions };
}
