import mongoose from 'mongoose';
import { legacyIdPlugin } from './plugins/legacyId.js';

const schema = new mongoose.Schema({
  key: { type: String, required: true, unique: true, index: true },
  value: { type: mongoose.Schema.Types.Mixed, default: null },
  description: { type: String, default: null },
}, { timestamps: { createdAt: 'created_at', updatedAt: 'updated_at' }, versionKey: false });
schema.plugin(legacyIdPlugin, { name: 'platform_settings' });
export const PlatformSetting = mongoose.model('PlatformSetting', schema);
