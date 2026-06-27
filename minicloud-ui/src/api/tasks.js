import client from './client';

export const getTasks = async (status = null) => {
  const params = status && status !== 'ALL' ? { status } : {};
  const response = await client.get('/tasks', { params });
  return response.data;
};

export const getTask = async (taskId) => {
  const response = await client.get(`/tasks/${taskId}`);
  return response.data;
};

export const submitTask = async (taskData) => {
  const response = await client.post('/tasks', taskData);
  return response.data;
};
