import mongoose from 'mongoose';
import { config, validateEnvironment } from './env.js';

export async function connectDatabase() {
  validateEnvironment();
  mongoose.set('strictQuery', true);
  return mongoose.connect(config.mongodbUri, { serverSelectionTimeoutMS: 10000 });
}

export const databaseReady = () => mongoose.connection.readyState === 1;
