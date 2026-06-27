import client from './client';

export const getLogs = async ({ nodeId, level, limit = 100 }) => {
  const params = { limit };
  if (nodeId && nodeId !== 'ALL') params.node_id = nodeId;
  if (level && level !== 'ALL') params.level = level;

  const response = await client.get('/logs', { params });
  return response.data;
};
