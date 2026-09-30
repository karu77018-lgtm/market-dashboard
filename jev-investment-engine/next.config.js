/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingIncludes: {
    '/api/python-check': ['./node_modules/pyodide/**/*'],
    '/api/feature-repro': ['./node_modules/pyodide/**/*'],
    '/api/build-strong-cases': ['./node_modules/pyodide/**/*'],
    '/api/stage4-score': ['./node_modules/pyodide/**/*']
  }
};
module.exports = nextConfig;
