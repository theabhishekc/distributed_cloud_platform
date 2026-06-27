import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://192.168.1.10:8000',
  timeout: 30000,
});

export default client;
