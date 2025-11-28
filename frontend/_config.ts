const config = {
  metadata: {
    title: 'SyftHub UI',
    description: 'Modern React application with TypeScript, Tailwind CSS and shadcn/ui components',
    keywords: 'syfthub, react, typescript, shadcn-ui, tailwindcss, vite'
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    // Use 127.0.0.1 for browser connections (0.0.0.0 is only for binding)
    testHost: '127.0.0.1'
  }
} as const;

export default config;
