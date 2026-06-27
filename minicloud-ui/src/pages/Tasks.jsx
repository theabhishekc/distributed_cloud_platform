import React, { useState } from 'react';
import { useTasks } from '../hooks/useTasks';
import TaskTable from '../components/TaskTable';
import TaskDrawer from '../components/TaskDrawer';
import TaskForm from '../components/TaskForm';
import ScanLine from '../components/ScanLine';

const STATUS_TABS = ['ALL', 'PENDING', 'RUNNING', 'COMPLETED', 'FAILED'];

const Tasks = () => {
  const { tasks, loading, error, statusFilter, setStatusFilter, addOptimisticTask } = useTasks(8000);
  const [selectedTask, setSelectedTask] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const getCountByStatus = (status) => {
    if (status === 'ALL') return tasks.length;
    return tasks.filter(t => t.status?.toUpperCase() === status).length;
  };

  return (
    <div className="relative h-full flex flex-col">
      <div className="flex justify-between items-end mb-6 border-b border-terminal-border pb-2">
        <div className="flex gap-6">
          {STATUS_TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setStatusFilter(tab)}
              className={`pb-2 border-b-2 transition-colors cursor-pointer text-sm font-bold tracking-widest ${
                statusFilter === tab
                  ? 'border-terminal-cyan text-terminal-cyan'
                  : 'border-transparent text-terminal-dim hover:text-gray-300'
              }`}
            >
              {tab} <span className="text-[10px] ml-1 opacity-70">[{getCountByStatus(tab)}]</span>
            </button>
          ))}
        </div>
        
        <button 
          onClick={() => setShowForm(!showForm)}
          className="border border-terminal-cyan text-terminal-cyan px-4 py-1 text-xs hover:bg-terminal-cyan hover:text-black transition-colors mb-2 cursor-pointer font-bold tracking-wider"
        >
          {showForm ? 'CLOSE FORM' : 'SUBMIT TASK'}
        </button>
      </div>

      {showForm && (
        <TaskForm 
          onCancel={() => setShowForm(false)} 
          onTaskSubmitted={(newTask) => addOptimisticTask(newTask)} 
        />
      )}

      {loading && tasks.length === 0 ? (
        <ScanLine text="FETCHING TASK QUEUE..." />
      ) : error && tasks.length === 0 ? (
        <div className="text-terminal-red p-4 border border-terminal-red/30 bg-terminal-red/10">ERR: {error}</div>
      ) : (
        <TaskTable 
          tasks={tasks} 
          onRowClick={(task) => setSelectedTask(task)} 
        />
      )}

      {selectedTask && (
        <TaskDrawer 
          task={selectedTask} 
          onClose={() => setSelectedTask(null)} 
        />
      )}
    </div>
  );
};

export default Tasks;
