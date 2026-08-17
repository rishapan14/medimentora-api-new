import mongoose from 'mongoose';
import { legacyIdPlugin } from './plugins/legacyId.js';
import { isAdminRole, roles, validRoles } from '../constants.js';

const userSchema = new mongoose.Schema({
  email: { type: String, required: true, unique: true, index: true, lowercase: true, trim: true, maxlength: 120 },
  password: { type: String, required: true, select: false },
  full_name: { type: String, default: null, maxlength: 150 },
  role: { type: String, required: true, enum: validRoles, default: roles.MEDICAL_STUDENT },
  previous_role: { type: String, default: null },
  speciality: { type: String, default: null, maxlength: 100 },
  bio: { type: String, default: null },
  reset_token: { type: String, default: null, select: false },
  reset_token_expires: { type: Date, default: null, select: false },
  is_active: { type: Boolean, default: true },
}, { timestamps: { createdAt: 'created_at', updatedAt: 'updated_at' }, versionKey: false });

userSchema.plugin(legacyIdPlugin, { name: 'users' });
userSchema.methods.toPublicJSON = function toPublicJSON(includeEmail = true) {
  const admin = isAdminRole(this.role);
  const data = {
    id: this.id, full_name: this.full_name, role: this.role, previous_role: this.previous_role,
    is_admin: admin, isAdmin: admin, panel_role: admin ? 'Admin' : 'User', speciality: this.speciality,
    bio: this.bio, is_active: this.is_active,
    created_at: this.created_at?.toISOString() ?? null, updated_at: this.updated_at?.toISOString() ?? null,
  };
  if (includeEmail) data.email = this.email;
  return data;
};

export const User = mongoose.model('User', userSchema);
