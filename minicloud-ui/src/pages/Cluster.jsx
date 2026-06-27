import React from 'react';
import { useNodes } from '../hooks/useNodes';
import NodeCard from '../components/NodeCard';
import ScanLine from '../components/ScanLine';

const Cluster = () => {
  const { nodes, loading, error } = useNodes(5000);

  if (loading && nodes.length === 0) {
    return <ScanLine text="FETCHING CLUSTER STATE..." />;
  }

  if (error && nodes.length === 0) {
    return <div className="text-terminal-red font-mono p-4">ERR: failed to fetch — {error}</div>;
  }

  const activeNodes = nodes.filter(n => n.status !== 'dead' && n.status !== 'offline');
  const healthyCount = activeNodes.filter(n => n.status !== 'degraded').length;
  
  const avgCpu = activeNodes.length > 0 
    ? activeNodes.reduce((acc, n) => acc + (n.cpu_percent || 0), 0) / activeNodes.length 
    : 0;
    
  const avgRam = activeNodes.length > 0 
    ? activeNodes.reduce((acc, n) => acc + (n.ram_percent || 0), 0) / activeNodes.length 
    : 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {nodes.map(node => (
          <NodeCard key={node.node_id} node={node} />
        ))}
        {nodes.length === 0 && !loading && (
          <div className="col-span-full text-terminal-dim">No nodes registered. <span className="animate-blink">_</span></div>
        )}
      </div>

      <div className="w-full bg-terminal-surface border border-terminal-border p-3 text-xs flex flex-wrap gap-6 items-center">
        <div>
          <span className="text-terminal-dim">NODES: </span>
          <span className={healthyCount === nodes.length && nodes.length > 0 ? 'text-terminal-green' : 'text-terminal-amber'}>
            {healthyCount}/{nodes.length} HEALTHY
          </span>
        </div>
        <div className="text-terminal-dim">|</div>
        <div>
          <span className="text-terminal-dim">TOTAL CPU AVG: </span>
          <span className="text-gray-200">{avgCpu.toFixed(1)}%</span>
        </div>
        <div className="text-terminal-dim">|</div>
        <div>
          <span className="text-terminal-dim">TOTAL RAM AVG: </span>
          <span className="text-gray-200">{avgRam.toFixed(1)}%</span>
        </div>
      </div>
    </div>
  );
};

export default Cluster;
