import app from './server.js';
const port = Number(process.env.PORT || 3001);
app.listen(port, '127.0.0.1', () => console.log(`SoundWorks API ready on port ${port}`));
