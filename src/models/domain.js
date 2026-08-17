import mongoose from 'mongoose';
import { legacyIdPlugin } from './plugins/legacyId.js';

const opts = { strict: false, versionKey: false, timestamps: { createdAt: 'created_at', updatedAt: 'updated_at' } };
const ref = (required = false) => ({ type: Number, required, index: true });
const create = (name, collection, fields, indexes = []) => {
  const s = new mongoose.Schema(fields, { ...opts, collection });
  s.plugin(legacyIdPlugin, { name: collection });
  indexes.forEach(([keys, options]) => s.index(keys, options));
  s.set('toJSON', { transform: (_doc, value) => { delete value._id; return value; } });
  return mongoose.models[name] || mongoose.model(name, s);
};

export const CourseCategory = create('CourseCategory', 'course_categories', { name: { type: String, required: true }, slug: { type: String, required: true, unique: true }, description: String });
export const Course = create('Course', 'courses', { title: { type: String, required: true }, description: String, category_id: ref(), instructor_id: ref(), difficulty: String, thumbnail_url: String, duration_hours: Number, is_published: { type: Boolean, default: false } });
export const Lesson = create('Lesson', 'lessons', { course_id: ref(true), title: { type: String, required: true }, content: String, order_index: { type: Number, default: 0 }, duration_minutes: Number, video_url: String });
export const LessonBookmark = create('LessonBookmark', 'lesson_bookmarks', { user_id: ref(true), lesson_id: ref(true) }, [[{ user_id: 1, lesson_id: 1 }, { unique: true }]]);
export const CompletedLesson = create('CompletedLesson', 'completed_lessons', { user_id: ref(true), lesson_id: ref(true), completed_at: { type: Date, default: Date.now } }, [[{ user_id: 1, lesson_id: 1 }, { unique: true }]]);
export const CourseProgress = create('CourseProgress', 'course_progress', { user_id: ref(true), course_id: ref(true), progress_percentage: { type: Number, default: 0 }, enrolled_at: { type: Date, default: Date.now }, completed_at: Date }, [[{ user_id: 1, course_id: 1 }, { unique: true }]]);
export const Recommendation = create('Recommendation', 'recommendations', { user_id: ref(true), recommendation_type: String, title: String, description: String, reference_id: Number, reason: String, is_viewed: { type: Boolean, default: false } });
export const Quiz = create('Quiz', 'quizzes', { title: { type: String, required: true }, description: String, category: String, difficulty: String, time_limit: Number, passing_score: Number, created_by: ref(), is_published: { type: Boolean, default: true } });
export const Question = create('Question', 'questions', { quiz_id: ref(true), question_text: { type: String, required: true }, question_type: String, options: [mongoose.Schema.Types.Mixed], correct_answer: mongoose.Schema.Types.Mixed, explanation: String, points: { type: Number, default: 1 } });
export const Result = create('Result', 'results', { user_id: ref(true), quiz_id: ref(true), score: Number, total_questions: Number, correct_answers: Number, answers: mongoose.Schema.Types.Mixed, completed_at: { type: Date, default: Date.now } });
export const Simulation = create('Simulation', 'simulations', { title: { type: String, required: true }, description: String, scenario: String, difficulty: String, category: String, patient_data: mongoose.Schema.Types.Mixed, correct_actions: mongoose.Schema.Types.Mixed, created_by: ref(), is_active: { type: Boolean, default: true } });
export const SimulationAttempt = create('SimulationAttempt', 'simulation_attempts', { user_id: ref(true), simulation_id: ref(true), actions: mongoose.Schema.Types.Mixed, score: Number, feedback: mongoose.Schema.Types.Mixed, completed_at: { type: Date, default: Date.now } });
export const ClinicalCase = create('ClinicalCase', 'clinical_cases', { title: { type: String, required: true }, description: String, patient_info: mongoose.Schema.Types.Mixed, symptoms: mongoose.Schema.Types.Mixed, diagnosis: String, treatment: mongoose.Schema.Types.Mixed, difficulty: String, specialty: String, created_by: ref() });
export const CaseFavorite = create('CaseFavorite', 'case_favorites', { user_id: ref(true), case_id: ref(true) }, [[{ user_id: 1, case_id: 1 }, { unique: true }]]);
export const Discussion = create('Discussion', 'discussions', { user_id: ref(true), title: { type: String, required: true }, content: { type: String, required: true }, category: String, tags: [String], likes_count: { type: Number, default: 0 } });
export const Comment = create('Comment', 'comments', { discussion_id: ref(true), user_id: ref(true), parent_id: ref(), content: { type: String, required: true }, likes_count: { type: Number, default: 0 } });
export const DiscussionLike = create('DiscussionLike', 'discussion_likes', { discussion_id: ref(true), user_id: ref(true) }, [[{ discussion_id: 1, user_id: 1 }, { unique: true }]]);
export const CommentLike = create('CommentLike', 'comment_likes', { comment_id: ref(true), user_id: ref(true) }, [[{ comment_id: 1, user_id: 1 }, { unique: true }]]);
export const Report = create('Report', 'reports', { user_id: ref(true), title: String, report_type: String, original_filename: String, stored_filename: String, file_path: String, file_type: String, file_size: Number, extracted_text: String, metadata: mongoose.Schema.Types.Mixed });
export const ReportAnalysis = create('ReportAnalysis', 'report_analyses', { user_id: ref(true), report_id: ref(), analysis_data: mongoose.Schema.Types.Mixed, summary: String, confidence: Number, status: { type: String, default: 'completed' } });
export const Progress = create('Progress', 'progress', { user_id: ref(true), learning_progress: { type: Number, default: 0 }, quiz_scores: mongoose.Schema.Types.Mixed, simulation_scores: mongoose.Schema.Types.Mixed, achievements: [mongoose.Schema.Types.Mixed], weak_topics: [mongoose.Schema.Types.Mixed], total_study_minutes: { type: Number, default: 0 } }, [[{ user_id: 1 }, { unique: true }]]);
export const Notification = create('Notification', 'notifications', { user_id: ref(true), notification_type: { type: String, required: true }, title: { type: String, required: true }, message: { type: String, required: true }, reference_id: Number, is_read: { type: Boolean, default: false } });
export const Certificate = create('Certificate', 'certificates', { user_id: ref(true), course_id: ref(true), certificate_number: { type: String, required: true, unique: true }, file_path: String, issued_at: { type: Date, default: Date.now } });
export const XrayAnalysis = create('XrayAnalysis', 'xray_analysis', { user_id: ref(true), filename: { type: String, required: true }, stored_filename: String, file_path: { type: String, required: true }, file_type: String, file_size: Number, patient_age: Number, gender: String, body_part: String, symptoms: String, reason_for_exam: String, status: { type: String, default: 'uploaded' }, possible_findings: mongoose.Schema.Types.Mixed, confidence: Number, ai_summary: String, disclaimer: String });
