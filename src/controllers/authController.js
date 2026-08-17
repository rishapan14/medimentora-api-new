import jwt from 'jsonwebtoken';
import { config } from '../config/env.js';
import { PlatformSetting } from '../models/PlatformSetting.js';
import { User } from '../models/User.js';
import { authService } from '../services/authService.js';
import { validateLogin, validateRegister, validateReset } from '../validations/auth.js';
import { failure, success } from '../utils/response.js';

export async function register(req, res) {
  const setting = await PlatformSetting.findOne({ key: 'allow_registrations' }).lean();
  if (setting && [false, 'false', 0].includes(setting.value)) return failure(res, 'New user registration is currently disabled.', 403);
  const email = String(req.body?.email ?? '').trim().toLowerCase();
  const errors = validateRegister(req.body, email ? Boolean(await User.exists({ email })) : false);
  if (errors.length) return failure(res, errors.length === 1 ? errors[0] : 'Validation failed.', 400, { errors });
  try { const user = await authService.register(req.body); return success(res, 'User registered successfully.', { user: user.toPublicJSON(), ...authService.tokens(user) }, 201); }
  catch (error) { if (error.code === 11000) return failure(res, 'Email address already exists.', 409); throw error; }
}
export async function login(req, res) {
  const errors = validateLogin(req.body); if (errors.length) return failure(res, 'Validation failed.', 400, { errors });
  const user = await authService.authenticate(req.body.email, req.body.password); if (!user) return failure(res, 'Invalid email or password.', 401);
  const setting = await PlatformSetting.findOne({ key: 'maintenance_mode' }).lean();
  if ([true, 'true', 1].includes(setting?.value) && !user.toPublicJSON().is_admin) return failure(res, 'MediMentora is temporarily in maintenance mode. Only administrators can sign in.', 503, { error_code: 'maintenance_mode' });
  return success(res, 'Login successful.', { user: user.toPublicJSON(), ...authService.tokens(user) });
}
export async function refresh(req, res) { return success(res, 'Token refreshed.', { access_token: jwt.sign({ sub: String(req.user.id), type: 'access', fresh: true }, config.jwtSecret, { expiresIn: `${config.jwtAccessMinutes}m` }) }); }
export async function forgotPassword(req, res) {
  if (!req.body?.email) return failure(res, 'Validation failed.', 400, { errors: ['email is required.'] });
  const result = await authService.requestReset(req.body.email); const data = { message: 'If the email exists, a reset link has been generated.' };
  if (result && config.debug) data.reset_link = result.reset_link; return success(res, 'Password reset initiated.', data);
}
export async function resetPassword(req, res) {
  const errors = validateReset(req.body); if (errors.length) return failure(res, 'Validation failed.', 400, { errors });
  try { const user = await authService.resetPassword(req.body.token, req.body.password); return success(res, 'Password reset successful.', { user: user.toPublicJSON() }); }
  catch (error) { return failure(res, error.message, 400); }
}
export async function profile(req, res) {
  if (req.method === 'GET') return success(res, 'Profile retrieved.', { user: req.user.toPublicJSON() });
  for (const key of ['full_name', 'speciality', 'bio']) if (key in req.body) req.user[key] = req.body[key];
  if (req.body.email) { const email = req.body.email.trim().toLowerCase(); if (await User.exists({ email, _id: { $ne: req.user._id } })) return failure(res, 'Email already in use.', 400); req.user.email = email; }
  await req.user.save(); return success(res, 'Profile updated.', { user: req.user.toPublicJSON() });
}
export async function logout(_req, res) { return success(res, 'Logged out successfully.'); }
