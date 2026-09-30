/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingIncludes: {
    '/api/numeric-v2-study': ['./node_modules/pyodide/**/*']
  }
};
module.exports = nextConfig;
