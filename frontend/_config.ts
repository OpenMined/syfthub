const config = {
  metadata: {
    title: 'SyftHub | The Gateway to Federated AI',
    description: 'Discover your peers on the Syft network. Choose and query trusted sources - with attribution, privacy, and control built in.',
    keywords: 'syfthub, openmined, pysyft, privacy, data science, federated learning, differential privacy',
    ogImage: 'https://syfthub.openmined.org/favicon/openmined-icon.svg'
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    // Use 127.0.0.1 for browser connections (0.0.0.0 is only for binding)
    testHost: '127.0.0.1'
  }
} as const;

export default config;
