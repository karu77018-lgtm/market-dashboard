/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingIncludes: {
    '/api/numeric-v2-study': ['./node_modules/pyodide/**/*'],
    '/api/numeric-v2-origin': ['./node_modules/pyodide/**/*']
  }
};
module.exports = nextConfig;
