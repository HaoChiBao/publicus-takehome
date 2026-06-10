/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Monorepo: skip sibling Python/pipeline folders during trace collection.
  outputFileTracingExcludes: {
    "*": [
      "../api/**",
      "../pipeline/**",
      "../data/**",
      "../supabase/**",
      "../scripts/**",
      "../.venv/**",
    ],
  },
  // Proxy API calls through Next.js in local dev only — production uses NEXT_PUBLIC_API_URL.
  async rewrites() {
    if (process.env.NODE_ENV === "production") {
      return [];
    }
    const backend =
      process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
