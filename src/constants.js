export const roles = Object.freeze({
  MEDICAL_STUDENT: 'medical_student', NURSE: 'nurse', DOCTOR: 'doctor', ADMIN: 'admin', SUPER_ADMIN: 'super_admin',
});
export const validRoles = Object.values(roles);
export const adminRoles = [roles.ADMIN, roles.SUPER_ADMIN];
export const isAdminRole = (role) => adminRoles.includes(role);
