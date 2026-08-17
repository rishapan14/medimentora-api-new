import path from 'node:path';
import crypto from 'node:crypto';
import multer from 'multer';
import { config } from '../config/env.js';

const storage = (folder) => multer.diskStorage({
  destination: path.join(config.uploadRoot, folder),
  filename: (_req, file, done) => done(null, `${crypto.randomUUID().replaceAll('-', '')}_${path.basename(file.originalname).replace(/[^a-zA-Z0-9._-]/g, '_')}`),
});
const accepted = (extensions) => (_req, file, done) => done(null, extensions.has(path.extname(file.originalname).toLowerCase()));
export const reportUpload = multer({ storage: storage('reports'), limits: { fileSize: 100 * 1024 * 1024, files: 20 }, fileFilter: accepted(new Set(['.pdf', '.png', '.jpg', '.jpeg', '.webp'])) });
export const xrayUpload = multer({ storage: storage('xrays'), limits: { fileSize: 50 * 1024 * 1024, files: 20 }, fileFilter: accepted(new Set(['.png', '.jpg', '.jpeg', '.webp', '.dcm', '.dicom'])) });
