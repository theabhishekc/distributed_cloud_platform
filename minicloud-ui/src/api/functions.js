import client from './client';

export const listFunctions = async () => {
  const response = await client.get('/functions');
  return response.data;
};

export const createFunction = async (fnData) => {
  const response = await client.post('/functions', fnData);
  return response.data;
};

export const invokeFunction = async (functionId, payload, timeout = 30) => {
  const response = await client.post(`/functions/${functionId}/invoke`, payload, {
    params: { timeout },
    timeout: timeout * 1000 + 5000,
  });
  return response.data;
};
