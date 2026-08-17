import 'dotenv/config';
import path from 'node:path';

const integer = (name, fallback) => {
  const value = Number.parseInt(process.env[name] ?? fallback, 10);
  if (!Number.isFinite(value)) throw new Error(`${name} must be an integer.`);
  return value;
};

const list = (value) => String(value ?? '').split(',').map((item) => item.trim()).filter(Boolean);
const root = process.cwd();

export const config = Object.freeze({
  nodeEnv: process.env.NODE_ENV ?? 'development',
  debug: String(process.env.DEBUG ?? process.env.FLASK_DEBUG ?? 'false').toLowerCase() === 'true',
  port: integer('PORT', 5000),
  mongodbUri: process.env.MONGODB_URI ?? '',
  jwtSecret: process.env.JWT_SECRET_KEY ?? process.env.SECRET_KEY ?? 'development-only-change-me',
  jwtAccessMinutes: integer('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', 30),
  jwtRefreshDays: integer('JWT_REFRESH_TOKEN_EXPIRES_DAYS', 7),
  corsOrigins: list(process.env.CORS_ORIGINS ?? 'http://localhost:3000,http://127.0.0.1:3000'),
  frontendUrl: process.env.FRONTEND_URL ?? 'http://localhost:3000',
  resetTokenHours: integer('RESET_TOKEN_EXPIRE_HOURS', 24),
  uploadRoot: path.resolve(root, process.env.UPLOAD_FOLDER ?? 'uploads'),
});

export function validateEnvironment() {
  if (!config.mongodbUri) throw new Error('MONGODB_URI is required.');
  if (config.nodeEnv === 'production' && config.jwtSecret === 'development-only-change-me') {
    throw new Error('JWT_SECRET_KEY is required in production.');
  }
}
