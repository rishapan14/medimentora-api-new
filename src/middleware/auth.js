import jwt from 'jsonwebtoken';
import { config } from '../config/env.js';
import { adminRoles } from '../constants.js';
import { User } from '../models/User.js';
import { failure } from '../utils/response.js';

export const authenticate = (options = {}) => async (req, res, next) => {
  try {
    const token = req.headers.authorization?.match(/^Bearer\s+(.+)$/i)?.[1];
    if (!token) return failure(res, 'Missing Authorization Header', 401);
    const payload = jwt.verify(token, config.jwtSecret);
    if (options.refresh && payload.type !== 'refresh') return failure(res, 'Only refresh tokens are allowed', 422);
    if (!options.refresh && payload.type === 'refresh') return failure(res, 'Only non-refresh tokens are allowed', 422);
    const user = await User.findOne({ id: Number(payload.sub), is_active: true });
    if (!user) return failure(res, 'Account is deactivated or no longer valid.', 403);
    req.user = user; req.jwt = payload; return next();
  } catch (error) {
    const expired = error.name === 'TokenExpiredError'; return failure(res, expired ? 'Token has expired' : 'Signature verification failed', expired ? 401 : 422);
  }
};
export const rolesRequired = (...allowed) => [authenticate(), (req, res, next) => allowed.includes(req.user.role) ? next() : failure(res, 'Access forbidden: insufficient permissions.', 403)];
export const adminRequired = rolesRequired(...adminRoles);
