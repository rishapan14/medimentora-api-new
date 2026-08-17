export const success = (res, message, data = null, statusCode = 200) =>
  res.status(statusCode).json({ status: 'success', message, data });

export const failure = (res, message, statusCode = 400, data = null) =>
  res.status(statusCode).json({ status: 'error', message, data });
