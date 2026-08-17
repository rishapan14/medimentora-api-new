import { Router } from 'express';
import * as ctrl from '../controllers/domainController.js';
import { asyncHandler } from '../utils/asyncHandler.js';
import { authenticate, rolesRequired } from '../middleware/auth.js';

const wrap = (handler) => asyncHandler(handler);
const protectedRouter = () => { const router = Router(); router.use(authenticate()); return router; };
const author = rolesRequired(...ctrl.authorRoles);

export const learningRouter = protectedRouter();
learningRouter.get('/categories', wrap(ctrl.courses.categories));
learningRouter.route('/courses').get(wrap(ctrl.courses.list)).post(author, wrap(ctrl.courses.create));
learningRouter.route('/courses/:course_id').get(wrap(ctrl.courses.get)).put(author, wrap(ctrl.courses.update)).delete(author, wrap(ctrl.courses.remove));
learningRouter.post('/courses/:course_id/enroll', wrap(ctrl.courses.enroll));
learningRouter.get('/courses/:course_id/lessons', wrap(ctrl.courses.lessons));
learningRouter.route('/lessons/:lesson_id').get(wrap(ctrl.courses.lesson)).put(author, wrap(ctrl.courses.updateLesson)).delete(author, wrap(ctrl.courses.removeLesson));
learningRouter.post('/lessons', author, wrap(ctrl.courses.createLesson));
learningRouter.route('/lessons/:lesson_id/bookmark').post(wrap(ctrl.courses.bookmark)).delete(wrap(ctrl.courses.bookmark));
learningRouter.get('/bookmarks', wrap(ctrl.courses.bookmarks));
learningRouter.post('/lessons/:lesson_id/complete', wrap(ctrl.courses.complete));
learningRouter.get('/completed-lessons', wrap(ctrl.courses.completed));
learningRouter.get('/course-progress', wrap(ctrl.courses.progress));
learningRouter.get('/recommendations', wrap(ctrl.courses.recommendations));

export const quizRouter = protectedRouter();
quizRouter.get('/leaderboard', wrap(ctrl.quizzes.leaderboard)); quizRouter.get('/results', wrap(ctrl.quizzes.results));
quizRouter.route('/').get(wrap(ctrl.quizzes.list)).post(author, wrap(ctrl.quizzes.create));
quizRouter.route('/:quiz_id').get(wrap(ctrl.quizzes.get)).put(author, wrap(ctrl.quizzes.update)).delete(author, wrap(ctrl.quizzes.remove));
quizRouter.post('/:quiz_id/questions', author, wrap(ctrl.quizzes.createQuestion));
quizRouter.route('/questions/:question_id').put(author, wrap(ctrl.quizzes.updateQuestion)).delete(author, wrap(ctrl.quizzes.removeQuestion));
quizRouter.post('/:quiz_id/submit', wrap(ctrl.quizzes.submit));

export const simulationRouter = protectedRouter();
simulationRouter.get('/history', wrap(ctrl.simulations.history)); simulationRouter.route('/').get(wrap(ctrl.simulations.list)).post(author, wrap(ctrl.simulations.create));
simulationRouter.route('/:simulation_id').get(wrap(ctrl.simulations.get)).put(author, wrap(ctrl.simulations.update)).delete(author, wrap(ctrl.simulations.remove));
simulationRouter.post('/:simulation_id/submit', wrap(ctrl.simulations.submit));

export const clinicalCaseRouter = protectedRouter();
clinicalCaseRouter.get('/favorites', wrap(ctrl.cases.favorites)); clinicalCaseRouter.route('/').get(wrap(ctrl.cases.list)).post(author, wrap(ctrl.cases.create));
clinicalCaseRouter.route('/:case_id').get(wrap(ctrl.cases.get)).put(author, wrap(ctrl.cases.update)).delete(author, wrap(ctrl.cases.remove));
clinicalCaseRouter.route('/:case_id/favorite').post(wrap(ctrl.cases.favorite)).delete(wrap(ctrl.cases.favorite));

export const discussionRouter = protectedRouter();
discussionRouter.route('/').get(wrap(ctrl.discussions.list)).post(wrap(ctrl.discussions.create));
discussionRouter.route('/:discussion_id').get(wrap(ctrl.discussions.get)).put(wrap(ctrl.discussions.update)).delete(wrap(ctrl.discussions.remove));
discussionRouter.post('/:discussion_id/comments', wrap(ctrl.discussions.comment)); discussionRouter.delete('/comments/:comment_id', wrap(ctrl.discussions.removeComment));
discussionRouter.post('/:discussion_id/like', wrap(ctrl.discussions.like)); discussionRouter.post('/comments/:comment_id/like', wrap(ctrl.discussions.likeComment));

export const notificationRouter = protectedRouter();
notificationRouter.route('/').get(wrap(ctrl.notifications.list)).post(...rolesRequired('admin'), wrap(ctrl.notifications.create));
notificationRouter.put('/read-all', wrap(ctrl.notifications.readAll)); notificationRouter.put('/:notification_id/read', wrap(ctrl.notifications.read)); notificationRouter.delete('/:notification_id', wrap(ctrl.notifications.remove));
notificationRouter.post('/learning-reminder', wrap(ctrl.notifications.reminder)); notificationRouter.post('/quiz-reminder', wrap(ctrl.notifications.reminder));

export const progressRouter = protectedRouter();
progressRouter.get('/', wrap(ctrl.progress.get)); progressRouter.get('/dashboard', wrap(ctrl.progress.dashboard)); progressRouter.get('/learning-dashboard', wrap(ctrl.progress.dashboard)); progressRouter.get('/achievements', wrap(ctrl.progress.achievements));

export const certificateRouter = protectedRouter();
certificateRouter.get('/', wrap(ctrl.certificates.list)); certificateRouter.post('/generate', wrap(ctrl.certificates.generate)); certificateRouter.get('/:certificate_id', wrap(ctrl.certificates.get));
