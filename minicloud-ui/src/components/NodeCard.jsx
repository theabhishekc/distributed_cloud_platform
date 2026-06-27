import React, { useEffect, useState } from 'react';
import StatusDot from './StatusDot';
import CpuBar from './CpuBar';

const NodeCard = ({ node }) => {
  const { node_id, ip, port, cpu_percent, ram_percent, active_tasks, status, last_heartbeat } = node;
  const isDead = status === 'dead' || status === 'offline';
  
  const [secondsAgo, setSecondsAgo] = useState(0);

  useEffect(() => {
    const calc = () => {
      if (!last_heartbeat) return 0;
      return Math.floor((Date.now() - new Date(last_heartbeat).getTime()) / 1000);
    };
    setSecondsAgo(calc());
    const interval = setInterval(() => setSecondsAgo(calc()), 1000);
    return () => clearInterval(interval);
  }, [last_heartbeat]);

  return (
    <div className={`relative p-4 border bg-terminal-surface ${isDead ? 'border-terminal-red' : 'border-terminal-border'} transition-colors duration-300`}>
      {isDead && (
        <div className="absolute inset-0 bg-terminal-red/10 flex items-center justify-center z-10 backdrop-blur-[1px]">
          <span className="text-terminal-red font-bold tracking-widest text-lg bg-terminal-surface px-4 py-1 border border-terminal-red">
            NODE UNREACHABLE
          </span>
        </div>
      )}

      <div className="flex justify-between items-start mb-4">
        <div>
          <div className="text-terminal-cyan font-bold text-sm">
            {node_id ? node_id.substring(0, 8) : 'UNKNOWN'}
          </div>
          <div className="text-terminal-dim text-xs mt-1">
            {ip}:{port}
          </div>
        </div>
        <StatusDot status={status} />
      </div>

      <div className="space-y-3">
        <CpuBar label="CPU" percentage={cpu_percent} />
        <CpuBar label="RAM" percentage={ram_percent} />
      </div>

      <div className="mt-4 pt-4 border-t border-terminal-border flex justify-between text-xs text-terminal-dim">
        <div>
          TASKS: <span className="text-gray-200">{active_tasks || 0}</span>
        </div>
        <div>
          LAST: <span className="text-gray-200">{secondsAgo}s ago</span>
        </div>
      </div>
    </div>
  );
};

export default NodeCard;
