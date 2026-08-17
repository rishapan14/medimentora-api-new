import { Router } from 'express';
import * as controller from '../controllers/authController.js';
import { authenticate } from '../middleware/auth.js';
import { asyncHandler } from '../utils/asyncHandler.js';
export const authRouter = Router();
authRouter.post('/register', asyncHandler(controller.register)); authRouter.post('/login', asyncHandler(controller.login));
authRouter.post('/refresh', authenticate({ refresh: true }), asyncHandler(controller.refresh)); authRouter.post('/forgot-password', asyncHandler(controller.forgotPassword));
authRouter.post('/reset-password', asyncHandler(controller.resetPassword)); authRouter.route('/profile').get(authenticate(), asyncHandler(controller.profile)).put(authenticate(), asyncHandler(controller.profile));
authRouter.post('/logout', authenticate(), asyncHandler(controller.logout));
