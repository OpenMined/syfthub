const config = {
  metadata: {
    title: 'SyftHub',
    description: 'Discover and connect to PySyft dataspaces. Search, explore, and collaborate on privacy-preserving data science projects powered by OpenMined.',
    keywords: 'syfthub, openmined, pysyft, privacy, data science, federated learning, differential privacy',
    ogImage: '/og-image.png'
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    // Use 127.0.0.1 for browser connections (0.0.0.0 is only for binding)
    testHost: '127.0.0.1'
  }
} as const;

export default config;
