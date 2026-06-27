import React, { useState } from 'react';
import { submitTask } from '../api/tasks';

const TaskForm = ({ onTaskSubmitted, onCancel }) => {
  const [formData, setFormData] = useState({
    image: 'ubuntu:latest',
    command: 'echo "Hello from MiniCloud!"',
    cpu_limit: 1.0,
    ram_limit_mb: 256,
    priority: 5,
    max_retries: 3
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'number' ? Number(value) : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const newTask = await submitTask(formData);
      onTaskSubmitted(newTask);
      onCancel(); // Close form
    } catch (err) {
      setError(err.message || 'Failed to submit task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-terminal-surface border border-terminal-cyan/50 p-4 mb-6 shadow-[0_0_15px_rgba(0,212,255,0.1)]">
      <div className="flex justify-between items-center mb-4 border-b border-terminal-border pb-2">
        <h3 className="text-terminal-cyan font-bold tracking-widest">NEW TASK SPECIFICATION</h3>
        <button onClick={onCancel} className="text-terminal-dim hover:text-white cursor-pointer">✕</button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <div className="text-terminal-red text-xs bg-terminal-red/10 p-2 border border-terminal-red">{error}</div>}
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-xs text-terminal-dim">IMAGE</label>
            <input 
              name="image" 
              value={formData.image} 
              onChange={handleChange}
              className="w-full bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none" 
              required 
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-terminal-dim">COMMAND</label>
            <input 
              name="command" 
              value={formData.command} 
              onChange={handleChange}
              className="w-full bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none font-mono" 
              required 
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-terminal-dim">CPU LIMIT (0.1 - 4.0)</label>
            <input 
              name="cpu_limit" 
              type="number" 
              step="0.1" 
              min="0.1" 
              max="4.0" 
              value={formData.cpu_limit} 
              onChange={handleChange}
              className="w-full bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none" 
              required 
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-terminal-dim">RAM LIMIT MB (64 - 4096)</label>
            <input 
              name="ram_limit_mb" 
              type="number" 
              step="64" 
              min="64" 
              max="4096" 
              value={formData.ram_limit_mb} 
              onChange={handleChange}
              className="w-full bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none" 
              required 
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-terminal-dim">PRIORITY (1 - 10)</label>
            <input 
              name="priority" 
              type="number" 
              min="1" 
              max="10" 
              value={formData.priority} 
              onChange={handleChange}
              className="w-full bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none" 
              required 
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button 
            type="submit" 
            disabled={submitting}
            className="bg-terminal-cyan/10 border border-terminal-cyan text-terminal-cyan px-6 py-2 text-sm font-bold tracking-widest hover:bg-terminal-cyan hover:text-black transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'SUBMITTING...' : 'EXECUTE'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default TaskForm;
