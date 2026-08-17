import { createApp } from './src/app.js';
import { config } from './src/config/env.js';
import { connectDatabase } from './src/config/database.js';

const app = createApp();

connectDatabase()
  .then(() => app.listen(config.port, () => console.log(`MediMentora API listening on ${config.port}`)))
  .catch((error) => {
    console.error('MongoDB connection failed:', error.message);
    process.exitCode = 1;
  });

export default app;
