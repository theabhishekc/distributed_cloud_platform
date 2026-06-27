import client from './client';

export const listFiles = async () => {
  const response = await client.get('/files');
  return response.data;
};

export const uploadFile = async (file, onProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await client.post('/storage/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percentCompleted);
      }
    },
  });
  return response.data;
};

export const downloadFile = (fileId) => {
  const url = `${client.defaults.baseURL}/storage/download/${fileId}`;
  window.open(url, '_blank');
};
