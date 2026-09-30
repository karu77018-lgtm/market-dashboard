/** @type {import('next').NextConfig} */
const nextConfig={outputFileTracingIncludes:{'/api/numeric-v2-analyze':['./node_modules/pyodide/**/*']}};
module.exports=nextConfig;
