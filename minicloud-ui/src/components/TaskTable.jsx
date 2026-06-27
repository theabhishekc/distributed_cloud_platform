import React from 'react';

const getStatusColor = (status) => {
  switch (status?.toUpperCase()) {
    case 'PENDING': return 'text-terminal-dim';
    case 'RUNNING': return 'text-terminal-cyan';
    case 'COMPLETED': return 'text-terminal-green';
    case 'FAILED': return 'text-terminal-red';
    default: return 'text-gray-200';
  }
};

const TaskTable = ({ tasks, onRowClick }) => {
  if (!tasks || tasks.length === 0) {
    return (
      <div className="w-full text-center py-8 text-terminal-dim font-mono border border-terminal-border bg-terminal-surface">
        NO TASKS FOUND <span className="animate-blink">_</span>
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto border border-terminal-border bg-terminal-surface">
      <table className="w-full text-left font-mono text-sm">
        <thead className="bg-terminal-bg text-terminal-dim text-xs border-b border-terminal-border">
          <tr>
            <th className="px-4 py-3 font-normal">TASK_ID</th>
            <th className="px-4 py-3 font-normal">IMAGE</th>
            <th className="px-4 py-3 font-normal">WORKER</th>
            <th className="px-4 py-3 font-normal">STATUS</th>
            <th className="px-4 py-3 font-normal">DURATION</th>
            <th className="px-4 py-3 font-normal">SUBMITTED</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-terminal-border">
          {tasks.map(task => (
            <tr 
              key={task.task_id} 
              onClick={() => onRowClick(task)}
              className="hover:bg-terminal-border/30 cursor-pointer transition-colors"
            >
              <td className="px-4 py-3 text-terminal-cyan">{task.task_id?.substring(0, 8)}</td>
              <td className="px-4 py-3 text-gray-200 truncate max-w-[200px]">{task.image}</td>
              <td className="px-4 py-3 text-terminal-dim">{task.worker_id?.substring(0, 8) || '-'}</td>
              <td className={`px-4 py-3 ${getStatusColor(task.status)}`}>{task.status?.toUpperCase()}</td>
              <td className="px-4 py-3 text-gray-200">{task.duration_seconds ? `${task.duration_seconds}s` : '-'}</td>
              <td className="px-4 py-3 text-terminal-dim">
                {task.started_at || task.created_at ? new Date(task.started_at || task.created_at).toLocaleTimeString() : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default TaskTable;
