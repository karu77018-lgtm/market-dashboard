/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingIncludes: {
    '/api/event-risk-study': ['./node_modules/pyodide/**/*'],
    '/api/dilution-hazard-study': ['./node_modules/pyodide/**/*'],
    '/api/event-family-hazard-study': ['./node_modules/pyodide/**/*']
  }
};
module.exports = nextConfig;
