import React, { useState, useEffect, useCallback } from 'react';
import { getLogs } from '../api/logs';
import { useNodes } from '../hooks/useNodes';
import LogTerminal from '../components/LogTerminal';

const Logs = () => {
  const { nodes } = useNodes(30000); // Poll nodes less frequently here
  
  const [logs, setLogs] = useState([]);
  const [filterNode, setFilterNode] = useState('ALL');
  const [filterLevel, setFilterLevel] = useState('ALL');
  const [limit, setLimit] = useState(100);
  
  const [liveMode, setLiveMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLogs = useCallback(async (isPolling = false) => {
    if (!isPolling) setLoading(true);
    try {
      const data = await getLogs({ nodeId: filterNode, level: filterLevel, limit });
      const newLogs = Array.isArray(data) ? data : data.logs || [];
      
      setLogs(prev => {
        if (!isPolling) return newLogs;
        // Deduplicate logs in live mode
        const existingIds = new Set(prev.map(l => l.log_id || l.id));
        const toAdd = newLogs.filter(l => !existingIds.has(l.log_id || l.id));
        return [...prev, ...toAdd].slice(-limit); // Keep up to limit
      });
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch logs');
    } finally {
      if (!isPolling) setLoading(false);
    }
  }, [filterNode, filterLevel, limit]);

  useEffect(() => {
    fetchLogs(false);
  }, [filterNode, filterLevel, limit, fetchLogs]);

  useEffect(() => {
    let interval;
    if (liveMode) {
      interval = setInterval(() => fetchLogs(true), 3000);
    }
    return () => clearInterval(interval);
  }, [liveMode, fetchLogs]);

  const handleClear = () => setLogs([]);

  return (
    <div className="h-full flex flex-col gap-4">
      <div className="flex flex-wrap gap-4 items-end bg-terminal-surface p-4 border border-terminal-border">
        <div className="space-y-1">
          <label className="text-[10px] text-terminal-dim">NODE_ID</label>
          <select 
            value={filterNode} 
            onChange={(e) => setFilterNode(e.target.value)}
            className="w-40 bg-terminal-bg border border-terminal-border p-1.5 text-xs text-gray-200 focus:border-terminal-cyan focus:outline-none"
          >
            <option value="ALL">ALL NODES</option>
            {nodes.map(n => (
              <option key={n.node_id} value={n.node_id}>{n.node_id.substring(0, 8)}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-terminal-dim">LEVEL</label>
          <select 
            value={filterLevel} 
            onChange={(e) => setFilterLevel(e.target.value)}
            className="w-32 bg-terminal-bg border border-terminal-border p-1.5 text-xs text-gray-200 focus:border-terminal-cyan focus:outline-none"
          >
            <option value="ALL">ALL</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-terminal-dim">LIMIT</label>
          <input 
            type="number" 
            value={limit} 
            onChange={(e) => setLimit(Number(e.target.value))}
            className="w-24 bg-terminal-bg border border-terminal-border p-1.5 text-xs text-gray-200 focus:border-terminal-cyan focus:outline-none"
            min="10" max="1000"
          />
        </div>

        <button 
          onClick={() => fetchLogs(false)}
          className="border border-terminal-cyan text-terminal-cyan px-4 py-1.5 text-xs hover:bg-terminal-cyan hover:text-black transition-colors font-bold tracking-widest cursor-pointer"
        >
          FETCH
        </button>

        <div className="flex-1" />

        <div className="flex items-center gap-2">
          <span className="text-[10px] text-terminal-dim">LIVE MODE</span>
          <button 
            onClick={() => setLiveMode(!liveMode)}
            className={`w-12 h-6 border cursor-pointer relative transition-colors ${liveMode ? 'border-terminal-green bg-terminal-green/20' : 'border-terminal-border bg-terminal-bg'}`}
          >
            <div className={`absolute top-1 bottom-1 w-4 bg-terminal-green transition-all ${liveMode ? 'right-1' : 'left-1 bg-terminal-dim'}`} />
          </button>
        </div>
      </div>

      {error && <div className="text-terminal-red text-xs bg-terminal-red/10 p-2 border border-terminal-red">{error}</div>}

      <LogTerminal logs={logs} onClear={handleClear} />
    </div>
  );
};

export default Logs;
