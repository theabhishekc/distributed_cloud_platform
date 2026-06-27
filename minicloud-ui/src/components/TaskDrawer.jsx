import React, { useEffect, useState } from 'react';
import { getTask } from '../api/tasks';
import ScanLine from './ScanLine';

const steps = ['SUBMITTED', 'SCHEDULED', 'RUNNING', 'COMPLETED'];

const TaskDrawer = ({ task, onClose }) => {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!task) return;
    const fetchDetails = async () => {
      setLoading(true);
      try {
        const data = await getTask(task.task_id);
        setDetails(data);
        setError(null);
      } catch (err) {
        setError(err.message || 'Failed to fetch task details');
      } finally {
        setLoading(false);
      }
    };
    fetchDetails();
  }, [task]);

  if (!task) return null;

  const currentStatus = details?.status || task.status;
  const isFailed = currentStatus === 'FAILED';
  
  // Map current status to step index
  let currentIndex = 0;
  if (currentStatus === 'PENDING') currentIndex = 0;
  if (currentStatus === 'SCHEDULED') currentIndex = 1;
  if (currentStatus === 'RUNNING') currentIndex = 2;
  if (currentStatus === 'COMPLETED' || currentStatus === 'FAILED') currentIndex = 3;

  return (
    <div className="fixed top-16 right-0 bottom-0 w-[400px] bg-terminal-surface border-l border-terminal-border flex flex-col shadow-2xl z-30 transition-transform transform translate-x-0">
      <div className="flex justify-between items-center p-4 border-b border-terminal-border">
        <h2 className="text-terminal-cyan font-bold truncate pr-4">TASK: {task.task_id}</h2>
        <button onClick={onClose} className="text-terminal-dim hover:text-white px-2 py-1 border border-transparent hover:border-terminal-border cursor-pointer">
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {loading ? (
          <ScanLine text="FETCHING TASK DETAILS..." />
        ) : error ? (
          <div className="text-terminal-red">ERR: {error}</div>
        ) : (
          <>
            <div className="space-y-1">
              <div className="text-xs text-terminal-dim">COMMAND</div>
              <div className="bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-300 font-mono">
                {details?.command || task.command || 'N/A'}
              </div>
            </div>

            <div className="space-y-2">
              <div className="text-xs text-terminal-dim">TIMELINE</div>
              <div className="flex items-center justify-between relative pt-2 pb-6">
                <div className="absolute top-4 left-0 right-0 h-[1px] bg-terminal-border z-0" />
                
                {steps.map((step, idx) => {
                  const isCompleted = idx < currentIndex || (idx === 3 && currentStatus === 'COMPLETED');
                  const isCurrent = idx === currentIndex && !isFailed && currentStatus !== 'COMPLETED';
                  const isError = idx === 3 && isFailed;

                  let dotColor = 'bg-terminal-border';
                  if (isCompleted) dotColor = 'bg-terminal-cyan shadow-[0_0_8px_rgba(0,212,255,0.5)]';
                  if (isCurrent) dotColor = 'bg-terminal-cyan animate-pulse';
                  if (isError) dotColor = 'bg-terminal-red shadow-[0_0_8px_rgba(239,68,68,0.5)]';

                  return (
                    <div key={step} className="relative z-10 flex flex-col items-center gap-2">
                      <div className={`w-3 h-3 rounded-full border-2 border-terminal-surface ${dotColor}`} />
                      <div className="absolute top-5 text-[9px] text-terminal-dim whitespace-nowrap">
                        {step}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {(details?.output || details?.error) && (
              <div className="space-y-1">
                <div className="text-xs text-terminal-dim">OUTPUT</div>
                <div className="bg-terminal-bg border border-terminal-border p-3 text-xs font-mono max-h-[300px] overflow-y-auto whitespace-pre-wrap">
                  {details?.error && (
                    <div className="text-terminal-red mb-2">{details.error}</div>
                  )}
                  {details?.output && (
                    <div className="text-terminal-green">{details.output}</div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default TaskDrawer;
