import client from './client';

export const getNodes = async () => {
  const response = await client.get('/registry/nodes');
  return response.data;
};
