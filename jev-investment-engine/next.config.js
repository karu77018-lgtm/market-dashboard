/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingIncludes: {
    '/api/python-check': [
      './node_modules/pyodide/**/*'
    ]
  }
};
module.exports = nextConfig;
