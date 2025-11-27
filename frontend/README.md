# SyftHub UI

Modern React application built with Vite, TypeScript, Tailwind CSS, and shadcn/ui components.

## Tech Stack

- **React 19** - Latest React with modern features
- **TypeScript** - Type-safe development
- **Vite 7** - Lightning-fast development server and build tool
- **Tailwind CSS 4** - Utility-first CSS framework
- **shadcn/ui** - Beautiful, accessible React components
- **React Router v7** - Client-side routing
- **ESLint 9 & Prettier** - Code quality and formatting
- **SWC** - Speedy Web Compiler for faster builds

## Getting Started

### Prerequisites

- Node.js 18+
- npm

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Available Scripts

- `npm run dev` - Start development server on port 3000
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run typecheck` - Check TypeScript types
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix ESLint errors
- `npm run format` - Format code with Prettier
- `npm run test` - Run tests with Playwright
- `npm run test:ui` - Run tests with Playwright UI

## Project Structure

```
syfthub-ui/
├── src/
│   ├── components/     # React components
│   │   ├── ui/         # shadcn/ui components
│   │   └── ...         # Custom components
│   ├── lib/            # Utility functions
│   ├── styles/         # Global styles
│   ├── assets/         # Static assets
│   ├── app.tsx         # Main app component
│   └── main.tsx        # Application entry point
├── public/             # Public assets
├── __tests__/          # Test files
└── ...config files
```

## Features

- ⚡ Fast development with Vite and SWC
- 🎨 Modern UI with shadcn/ui components
- 🎯 Type-safe with TypeScript
- 🎨 Styled with Tailwind CSS 4
- 📦 Optimized production builds
- 🧪 Testing with Playwright
- 🔧 Pre-configured ESLint and Prettier
- 🪝 Git hooks with Husky
- 🌙 Dark mode support

## License

MIT
