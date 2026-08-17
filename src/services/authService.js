import crypto from 'node:crypto';
import jwt from 'jsonwebtoken';
import { config } from '../config/env.js';
import { roles } from '../constants.js';
import { User } from '../models/User.js';
import { hashPassword, verifyPassword } from '../utils/password.js';

const sign = (user, type, expiresIn) => jwt.sign({ sub: String(user.id), type, fresh: type === 'access' }, config.jwtSecret, { expiresIn });
export const authService = {
  async register({ email, password, full_name }) {
    return User.create({ email: email.trim().toLowerCase(), password: await hashPassword(password), full_name: full_name.trim(), role: roles.MEDICAL_STUDENT });
  },
  async authenticate(email, password) {
    const user = await User.findOne({ email: email.trim().toLowerCase() }).select('+password');
    if (!user || !(await verifyPassword(password, user.password))) return null;
    if (!user.is_active) { const error = new Error('Account is deactivated.'); error.status = 403; throw error; }
    return user;
  },
  tokens(user) { return { access_token: sign(user, 'access', `${config.jwtAccessMinutes}m`), refresh_token: sign(user, 'refresh', `${config.jwtRefreshDays}d`) }; },
  async requestReset(email) {
    const user = await User.findOne({ email: email.trim().toLowerCase() }).select('+reset_token +reset_token_expires');
    if (!user) return null;
    user.reset_token = crypto.randomBytes(32).toString('base64url'); user.reset_token_expires = new Date(Date.now() + config.resetTokenHours * 3600000);
    await user.save(); return { reset_link: `${config.frontendUrl}/auth/reset-password?token=${user.reset_token}` };
  },
  async resetPassword(token, password) {
    const user = await User.findOne({ reset_token: token }).select('+reset_token +reset_token_expires +password');
    if (!user) throw new Error('Invalid or expired reset token.');
    if (user.reset_token_expires && user.reset_token_expires < new Date()) throw new Error('Reset token has expired.');
    user.password = await hashPassword(password); user.reset_token = null; user.reset_token_expires = null; return user.save();
  },
};
