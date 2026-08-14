const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Prevent Next from picking up C:\Users\Admin\package-lock.json as monorepo root.
  outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
