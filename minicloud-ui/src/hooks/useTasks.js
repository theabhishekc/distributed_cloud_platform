import { useState, useEffect, useCallback } from 'react';
import { getTasks } from '../api/tasks';
import { usePolling } from './usePolling';

export const useTasks = (pollingInterval = 8000) => {
  const [tasks, setTasks] = useState([]);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchTasks = useCallback(async (isPolling = false) => {
    if (!isPolling) setLoading(true);
    try {
      const data = await getTasks(statusFilter);
      setTasks(Array.isArray(data) ? data : data.tasks || []);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch tasks');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchTasks(false);
  }, [fetchTasks]);

  usePolling(() => {
    fetchTasks(true);
  }, pollingInterval);

  const addOptimisticTask = (newTask) => {
    setTasks((prev) => [newTask, ...prev]);
  };

  return {
    tasks,
    loading,
    error,
    statusFilter,
    setStatusFilter,
    refetch: fetchTasks,
    addOptimisticTask,
  };
};
