import fs from 'node:fs';
import cors from 'cors';
import express from 'express';
import mongoose from 'mongoose';
import { config } from './config/env.js';
import { databaseReady } from './config/database.js';
import { authRouter } from './routes/auth.js';
import { failure } from './utils/response.js';

export function createApp() {
  const app = express(); fs.mkdirSync(config.uploadRoot, { recursive: true }); app.disable('x-powered-by');
  app.use(cors({ origin: config.corsOrigins, methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'], allowedHeaders: ['Authorization', 'Content-Type', 'Accept'], exposedHeaders: ['Content-Disposition'], maxAge: 600 }));
  app.use(express.json({ limit: process.env.MAX_CONTENT_LENGTH || '102mb' })); app.use(express.urlencoded({ extended: true }));
  app.get('/', (_req, res) => res.json({ status: 'success', message: 'AI-Powered Clinical Report Analysis & Nursing Assistance Platform API', data: { version: '1.0.0', docs: { xray_swagger_ui: '/apidocs', xray_openapi: '/apispec/xray.yaml', xray_openapi_meta: '/apispec/xray' }, modules: { auth: '/api/auth', reports: '/api/reports', analysis: '/api/analysis', learning: '/api/learning', medical_teacher: '/api/medical-teacher', xray: '/api/xray', clinical_cases: '/api/clinical-cases', simulations: '/api/simulations', quizzes: '/api/quizzes', progress: '/api/progress', certificates: '/api/certificates', discussions: '/api/discussions', notifications: '/api/notifications' } } }));
  app.get('/health', (_req, res) => res.json({ status: 'ok', service: 'medimentora-api' }));
  app.get('/ready', async (_req, res) => { if (!databaseReady()) return res.status(503).json({ status: 'error', service: 'medimentora-api', database_schema: 'unreachable' }); const collections = await mongoose.connection.db.listCollections().toArray(); return res.json({ status: 'ok', service: 'medimentora-api', database_schema: 'ready', table_count: collections.length }); });
  app.use('/api/auth', authRouter); app.use((_req, res) => failure(res, 'Resource not found.', 404));
  app.use((error, _req, res, _next) => { console.error(error); if (error.name === 'ValidationError') return failure(res, 'Validation failed.', 400); if (error.code === 11000) return failure(res, 'Duplicate data.', 409); return failure(res, config.debug ? error.message : 'An internal server error occurred.', error.status || 500); });
  return app;
}
