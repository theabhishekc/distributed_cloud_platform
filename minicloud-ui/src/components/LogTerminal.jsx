import React, { useRef, useEffect } from 'react';

const LogTerminal = ({ logs, onClear }) => {
  const containerRef = useRef(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="relative flex-1 bg-[#050508] border border-terminal-border font-mono text-xs overflow-hidden flex flex-col">
      <div className="absolute top-2 right-2 flex gap-2">
        <button 
          onClick={onClear}
          className="bg-terminal-surface border border-terminal-border text-terminal-dim px-2 py-1 hover:text-white hover:border-terminal-cyan cursor-pointer z-10 transition-colors"
        >
          CLEAR
        </button>
      </div>

      <div ref={containerRef} className="flex-1 overflow-y-auto p-4 space-y-1">
        {logs.length === 0 ? (
          <div className="text-terminal-dim italic">Waiting for logs... <span className="animate-blink">_</span></div>
        ) : (
          logs.map((log) => {
            let levelColor = 'text-gray-300';
            const level = log.level?.toUpperCase();
            if (level === 'INFO') levelColor = 'text-gray-300 opacity-80';
            if (level === 'WARNING' || level === 'WARN') levelColor = 'text-terminal-amber';
            if (level === 'ERROR') levelColor = 'text-terminal-red';

            return (
              <div key={log.log_id || Math.random().toString()} className="flex gap-3 hover:bg-white/5 px-1 rounded-sm">
                <span className="text-terminal-dim shrink-0">
                  [{new Date(log.timestamp).toISOString().replace('T', ' ').substring(0, 19)}]
                </span>
                <span className={`${levelColor} shrink-0 w-16`}>
                  [{level}]
                </span>
                <span className="text-terminal-cyan shrink-0">
                  [{log.node_id?.substring(0, 8) || 'MASTER'}]
                </span>
                <span className="text-gray-200 break-all">
                  {log.message}
                </span>
              </div>
            );
          })
        )}
      </div>
      
      <div className="h-6 bg-terminal-surface border-t border-terminal-border flex justify-end items-center px-4 text-[10px] text-terminal-dim">
        SHOWING {logs.length} ENTRIES
      </div>
    </div>
  );
};

export default LogTerminal;
