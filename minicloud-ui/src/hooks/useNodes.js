import { useState, useEffect, useCallback } from 'react';
import { getNodes } from '../api/nodes';
import { usePolling } from './usePolling';

export const useNodes = (pollingInterval = 5000) => {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchNodes = useCallback(async (isPolling = false) => {
    if (!isPolling) setLoading(true);
    try {
      const data = await getNodes();
      // Ensure data is array
      setNodes(Array.isArray(data) ? data : data.nodes || []);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch nodes');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNodes(false);
  }, [fetchNodes]);

  usePolling(() => {
    fetchNodes(true);
  }, pollingInterval);

  return { nodes, loading, error, refetch: fetchNodes };
};
