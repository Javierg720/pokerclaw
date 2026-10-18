import { useState, useRef, useEffect } from 'react';
import { MessageCircle, Send, X, Flame, Skull, Hand, Eye, DollarSign, Crown } from 'lucide-react';

const REACTIONS = [
  { key: 'fire', icon: Flame, color: '#FF6B3D' },
  { key: 'skull', icon: Skull, color: '#FFFFFF' },
  { key: 'clap', icon: Hand, color: '#FFE600' },
  { key: 'eyes', icon: Eye, color: '#00F0FF' },
  { key: 'money', icon: DollarSign, color: '#4ADE80' },
  { key: 'crown', icon: Crown, color: '#FFE600' },
];

export function ChatPanel({ chatMessages, reactions, onSendChat, onSendReaction, username, onOpenChange }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const scrollRef = useRef(null);
  const unread = useRef(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const latestAgentMessage = [...chatMessages].reverse().find((msg) => msg.sender_type === 'agent');

  const setPanelOpen = (value) => {
    setOpen(value);
    onOpenChange?.(value);
  };

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      unread.current = 0;
      setUnreadCount(0);
    } else if (!open && chatMessages.length > 0) {
      unread.current++;
      setUnreadCount(unread.current);
    }
  }, [chatMessages, open]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSendChat(trimmed);
    setText('');
  };

  return (
    <>
      {/* Floating reactions */}
      <div className="fixed bottom-24 right-4 z-50 pointer-events-none" data-testid="reactions-overlay">
        {reactions.map((r) => {
          const def = REACTIONS.find(rx => rx.key === r.emoji);
          if (!def) return null;
          const Icon = def.icon;
          return (
            <div
              key={r.id}
              className="animate-float-up opacity-0"
              style={{ color: def.color }}
            >
              <Icon size={24} />
            </div>
          );
        })}
      </div>

      {/* Chat toggle button */}
      {!open && (
        <>
          {latestAgentMessage && unreadCount > 0 && (
            <button
              type="button"
              onClick={() => { setPanelOpen(true); unread.current = 0; setUnreadCount(0); }}
              className="fixed bottom-24 right-20 z-50 max-w-[190px] rounded-xl rounded-br-sm border border-[#00F0FF]/20 bg-[#071014]/95 px-3 py-2 text-left shadow-xl backdrop-blur"
              data-testid="agent-banter-preview"
            >
              <span className="block text-[8px] font-black tracking-widest text-[#00F0FF] uppercase">{latestAgentMessage.username} · BOT</span>
              <span className="block text-[10px] text-white/70 truncate">{latestAgentMessage.text}</span>
            </button>
          )}
          <button
            onClick={() => { setPanelOpen(true); unread.current = 0; setUnreadCount(0); }}
            data-testid="chat-toggle-btn"
            className="fixed bottom-24 right-4 z-50 w-12 h-12 rounded-full bg-[#FF003C] flex items-center justify-center shadow-lg shadow-[#FF003C]/20 hover:scale-105 transition-transform"
          >
            <MessageCircle size={22} strokeWidth={2.5} className="text-white" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-[#00F0FF] text-[9px] font-black text-black flex items-center justify-center">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>
        </>
      )}

      {/* Chat panel */}
      {open && (
        <div
          className="fixed bottom-24 right-3 z-50 w-72 max-h-[360px] flex flex-col rounded-2xl overflow-hidden border border-white/10"
          style={{ background: 'rgba(10,10,15,0.95)', backdropFilter: 'blur(20px)' }}
          data-testid="chat-panel"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-white/[0.06]">
            <div>
              <span className="block text-[11px] font-bold text-white/70 uppercase tracking-widest">Table Talk</span>
              <span className="block text-[8px] text-[#00F0FF]/60">Humans + clearly labeled agents</span>
            </div>
            <button onClick={() => setPanelOpen(false)} data-testid="chat-close-btn" className="text-white/30 hover:text-white">
              <X size={14} />
            </button>
          </div>

          {/* Reactions bar */}
          <div className="flex items-center justify-center gap-2 px-3 py-1.5 border-b border-white/[0.04]" data-testid="reactions-bar">
            {REACTIONS.map(({ key, icon: Icon, color }) => (
              <button
                key={key}
                onClick={() => onSendReaction(key)}
                data-testid={`reaction-${key}`}
                className="p-1.5 rounded-lg hover:bg-white/[0.06] transition-colors active:scale-90"
                title={key}
              >
                <Icon size={16} style={{ color }} />
              </button>
            ))}
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5 min-h-[120px] max-h-[200px]" data-testid="chat-messages">
            {chatMessages.length === 0 && (
              <p className="text-white/15 text-[10px] text-center py-4">No messages yet. Say something!</p>
            )}
            {chatMessages.map((msg, i) => (
              <div key={msg.id || i} className={`text-[11px] rounded-lg px-2 py-1.5 ${msg.sender_type === 'agent' ? 'bg-[#00F0FF]/[0.045] border border-[#00F0FF]/10' : ''}`}>
                <span className={`font-bold ${msg.sender_type === 'agent' ? 'text-[#00F0FF]' : 'text-white/70'}`}>{msg.username}</span>
                {msg.sender_type === 'agent' && (
                  <span className="ml-1 rounded bg-[#00F0FF]/15 px-1 py-0.5 text-[7px] font-black tracking-wider text-[#00F0FF]">BOT</span>
                )}
                <span className="text-white/60 ml-1.5">{msg.text}</span>
                {msg.sender_type === 'agent' && msg.personality && (
                  <span className="block mt-0.5 text-[8px] text-white/25">{msg.personality} · {msg.source === 'scripted_banter' ? 'scripted banter' : 'OpenClaw-authored'}</span>
                )}
              </div>
            ))}
          </div>

          {/* Input */}
          <div className="flex items-center gap-2 px-3 py-2 border-t border-white/[0.06]">
            <input
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Type a message..."
              data-testid="chat-input"
              className="flex-1 bg-white/[0.04] border border-white/[0.08] rounded-lg px-2.5 py-1.5 text-[11px] text-white placeholder-white/20 outline-none focus:border-[#FF003C]/30"
            />
            <button
              onClick={handleSend}
              data-testid="chat-send-btn"
              className="text-[#FF003C] hover:text-white transition-colors"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
