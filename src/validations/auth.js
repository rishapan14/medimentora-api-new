const emailPattern = /^[\w.-]+@[\w.-]+\.\w+$/;
export const validateRegister = (data, exists = false) => {
  if (!data) return ['Request body is required.'];
  const errors = []; const email = String(data.email ?? '').trim().toLowerCase();
  if (!email) errors.push('email is required.'); else if (!emailPattern.test(email)) errors.push('Invalid email format.'); else if (exists) errors.push('Email address already exists.');
  if (!String(data.password ?? '').trim()) errors.push('password is required.'); else if (String(data.password).length < 6) errors.push('password must be at least 6 characters.');
  const name = String(data.full_name ?? '').trim(); if (!name) errors.push('full_name is required.'); else if (name.length < 2) errors.push('full_name must be at least 2 characters.');
  if (data.role && data.role !== 'medical_student') errors.push('role cannot be assigned during public registration.'); return errors;
};
export const validateLogin = (data) => !data ? ['Request body is required.'] : [...(!data.email ? ['email is required.'] : []), ...(!data.password ? ['password is required.'] : [])];
export const validateReset = (data) => !data ? ['Request body is required.'] : [...(!data.token ? ['token is required.'] : []), ...(!data.password ? ['password is required.'] : String(data.password).length < 6 ? ['password must be at least 6 characters.'] : [])];
