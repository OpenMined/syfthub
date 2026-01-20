import React, { useState } from 'react';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import Box from 'lucide-react/dist/esm/icons/box';
import Check from 'lucide-react/dist/esm/icons/check';
import Code2 from 'lucide-react/dist/esm/icons/code-2';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Terminal from 'lucide-react/dist/esm/icons/terminal';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { PageHeader } from './ui/page-header';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';

interface BuildViewProperties {
  onAuthRequired?: () => void;
}

export function BuildView({ onAuthRequired: _onAuthRequired }: Readonly<BuildViewProperties>) {
  return (
    <div className='bg-syft-background min-h-screen'>
      <PageHeader title='Build' path='~/build' />

      {/* Main Content */}
      <div className='mx-auto max-w-5xl space-y-8 px-6 py-8'>
        {/* Hero / Intro Section */}
        <div className='max-w-3xl space-y-4'>
          <div className='bg-syft-surface text-syft-muted inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium'>
            <Code2 className='h-3 w-3' />
            Developer Portal
          </div>
          <h1 className='font-rubik text-syft-primary text-3xl font-medium'>
            Build privacy-first AI apps
          </h1>
          <p className='font-inter text-syft-muted text-lg leading-relaxed'>
            Access high-value data and models you don't own through a unified, permissioned API.
            Choose your stack and start building in minutes.
          </p>
        </div>

        {/* Tabs Section */}
        <Tabs defaultValue='python' className='space-y-8'>
          <div className='flex items-center justify-between overflow-x-auto pb-2'>
            <TabsList className='border-syft-border bg-syft-surface h-auto flex-shrink-0 border p-1'>
              <TabsTrigger
                value='python'
                className='text-syft-muted data-[state=active]:text-syft-primary px-4 py-2 data-[state=active]:bg-white'
              >
                Python SDK
              </TabsTrigger>
              <TabsTrigger
                value='javascript'
                className='text-syft-muted data-[state=active]:text-syft-primary px-4 py-2 data-[state=active]:bg-white'
              >
                JavaScript SDK
              </TabsTrigger>
              <TabsTrigger
                value='mcp'
                className='text-syft-muted data-[state=active]:text-syft-primary px-4 py-2 data-[state=active]:bg-white'
              >
                MCP Integration
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent
            value='python'
            className='animate-in fade-in slide-in-from-bottom-2 space-y-6 duration-500'
          >
            <div className='grid grid-cols-1 gap-8 lg:grid-cols-3'>
              <div className='space-y-6 lg:col-span-2'>
                <Section
                  title='Installation'
                  description='Install the SyftHub SDK via pip or uv.'
                  icon={<Box className='h-5 w-5' />}
                >
                  <CodeBlock code='pip install syfthub-sdk' language='bash' />
                </Section>

                <Section
                  title='Quick Start'
                  description='Initialize the client and start browsing endpoints.'
                  icon={<Terminal className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`from syfthub_sdk import SyftHubClient

# Initialize client
client = SyftHubClient(base_url="https://hub.syft.com")

# Login to your account
user = client.auth.login(username="alice", password="secret123")
print(f"Logged in as {user.username}")

# Browse public endpoints
for endpoint in client.hub.browse():
    print(f"{endpoint.path}: {endpoint.name}")

# Get a specific endpoint
endpoint = client.hub.get("alice/my-model")
print(endpoint.readme)`}
                    language='python'
                  />
                </Section>

                <Section
                  title='Manage Your Endpoints'
                  description='Create and manage your own endpoints.'
                  icon={<Code2 className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`# Create an endpoint
endpoint = client.my_endpoints.create(
    name="My Model",
    visibility="public",
    description="A machine learning model",
    readme="# My Model\\n\\nDocumentation here."
)
print(f"Created: {endpoint.slug}")

# List your endpoints
for ep in client.my_endpoints.list():
    print(f"{ep.name} ({ep.visibility})")`}
                    language='python'
                  />
                </Section>
              </div>

              <div className='space-y-6'>
                <InfoCard
                  title='Python SDK Features'
                  items={[
                    'Full type hints support',
                    'Lazy pagination iterators',
                    'Context manager support',
                    'Automatic token refresh'
                  ]}
                />
                <Card>
                  <CardHeader>
                    <CardTitle className='text-sm font-medium'>Resources</CardTitle>
                  </CardHeader>
                  <CardContent className='grid gap-2'>
                    <ResourceLink label='API Reference' />
                    <ResourceLink label='Example Notebooks' />
                    <ResourceLink label='Github Repository' />
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent
            value='javascript'
            className='animate-in fade-in slide-in-from-bottom-2 space-y-6 duration-500'
          >
            <div className='grid grid-cols-1 gap-8 lg:grid-cols-3'>
              <div className='space-y-6 lg:col-span-2'>
                <Section
                  title='Installation'
                  description='Install the SyftHub SDK via npm, yarn, or pnpm.'
                  icon={<Box className='h-5 w-5' />}
                >
                  <CodeBlock code='npm install @syfthub/sdk' language='bash' />
                </Section>

                <Section
                  title='Quick Start'
                  description='Initialize the client and start browsing endpoints.'
                  icon={<Terminal className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`import { SyftHubClient } from '@syfthub/sdk';

// Initialize client
const client = new SyftHubClient({
  baseUrl: 'https://hub.syft.com'
});

// Login to your account
const user = await client.auth.login('alice', 'secret123');
console.log(\`Logged in as \${user.username}\`);

// Browse public endpoints
for await (const endpoint of client.hub.browse()) {
  console.log(\`\${endpoint.ownerUsername}/\${endpoint.slug}: \${endpoint.name}\`);
}

// Get a specific endpoint
const endpoint = await client.hub.get('alice/my-model');
console.log(endpoint.readme);`}
                    language='typescript'
                  />
                </Section>

                <Section
                  title='Manage Your Endpoints'
                  description='Create and manage your own endpoints.'
                  icon={<Code2 className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`import { EndpointType, Visibility } from '@syfthub/sdk';

// Create an endpoint
const endpoint = await client.myEndpoints.create({
  name: 'My Model',
  type: EndpointType.MODEL,
  visibility: Visibility.PUBLIC,
  description: 'A machine learning model',
  readme: '# My Model\\n\\nDocumentation here.',
});
console.log(\`Created: \${endpoint.slug}\`);

// List your endpoints
for await (const ep of client.myEndpoints.list()) {
  console.log(\`\${ep.name} (\${ep.visibility})\`);
}`}
                    language='typescript'
                  />
                </Section>
              </div>

              <div className='space-y-6'>
                <InfoCard
                  title='TypeScript SDK Features'
                  items={[
                    'Full TypeScript support',
                    'Async iterators for pagination',
                    'Runs on Node.js & browsers',
                    'Automatic token refresh'
                  ]}
                />
                <Card>
                  <CardHeader>
                    <CardTitle className='text-sm font-medium'>Resources</CardTitle>
                  </CardHeader>
                  <CardContent className='grid gap-2'>
                    <ResourceLink label='Documentation' />
                    <ResourceLink label='Next.js Starter' />
                    <ResourceLink label='Github Repository' />
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent
            value='mcp'
            className='animate-in fade-in slide-in-from-bottom-2 space-y-6 duration-500'
          >
            <div className='grid grid-cols-1 gap-8 lg:grid-cols-3'>
              <div className='space-y-6 lg:col-span-2'>
                <Section
                  title='Configuration'
                  description='Add SyftHub to your MCP settings file.'
                  icon={<Box className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`{
  "mcpServers": {
    "syfthub": {
      "command": "npx",
      "args": ["-y", "@syfthub/mcp-server"],
      "env": {
        "SYFTHUB_URL": "https://hub.syft.com"
      }
    }
  }
}`}
                    language='json'
                  />
                </Section>

                <div className='flex gap-4 rounded-lg border border-blue-100 bg-blue-50 p-4'>
                  <div className='min-w-[24px] pt-1'>
                    <div className='flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600'>
                      i
                    </div>
                  </div>
                  <div>
                    <h4 className='text-syft-primary mb-1 font-medium'>What is MCP?</h4>
                    <p className='text-syft-muted text-sm'>
                      The Model Context Protocol (MCP) allows AI assistants like Claude to directly
                      browse and interact with SyftHub endpoints during conversation. Once
                      configured, you can ask your AI to explore available models and data sources
                      in real-time.
                    </p>
                  </div>
                </div>
              </div>

              <div className='space-y-6'>
                <InfoCard
                  title='MCP Features'
                  items={[
                    'Direct LLM integration',
                    'Browse endpoints via Claude',
                    'Works with Claude Desktop'
                  ]}
                />
                <Card>
                  <CardHeader>
                    <CardTitle className='text-sm font-medium'>Resources</CardTitle>
                  </CardHeader>
                  <CardContent className='grid gap-2'>
                    <ResourceLink label='MCP Specification' />
                    <ResourceLink label='Setup Guide' />
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

function Section({
  title,
  description,
  icon,
  children
}: Readonly<{
  title: string;
  description: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}>) {
  return (
    <div className='space-y-4'>
      <div className='flex items-start gap-3'>
        <div className='border-syft-border text-syft-primary rounded-lg border bg-white p-2'>
          {icon}
        </div>
        <div>
          <h3 className='text-syft-primary text-lg font-medium'>{title}</h3>
          <p className='text-syft-muted text-sm'>{description}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function CodeBlock({ code, language }: Readonly<{ code: string; language: string }>) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  };

  // Custom style to match the existing dark theme
  const customStyle = {
    ...vscDarkPlus,
    'pre[class*="language-"]': {
      ...vscDarkPlus['pre[class*="language-"]'],
      background: 'transparent',
      margin: 0,
      padding: 0,
      fontSize: '14px',
      lineHeight: '1.5'
    },
    'code[class*="language-"]': {
      ...vscDarkPlus['code[class*="language-"]'],
      background: 'transparent',
      fontSize: '14px',
      lineHeight: '1.5'
    }
  };

  return (
    <div className='group border-syft-border relative overflow-hidden rounded-xl border bg-[#1a1923]'>
      <div className='absolute top-2 right-2 opacity-0 transition-opacity group-hover:opacity-100'>
        <Button
          variant='ghost'
          size='icon'
          className='h-8 w-8 text-gray-400 hover:bg-white/10 hover:text-white'
          onClick={copyToClipboard}
        >
          {copied ? <Check className='h-4 w-4' /> : <Copy className='h-4 w-4' />}
        </Button>
      </div>
      <div className='flex items-center justify-between border-b border-white/5 bg-[#131219] px-4 py-2'>
        <span className='font-mono text-xs text-gray-400'>{language}</span>
      </div>
      <div className='overflow-x-auto p-4'>
        <SyntaxHighlighter
          language={language}
          style={customStyle}
          customStyle={{
            background: 'transparent',
            padding: 0,
            margin: 0
          }}
          codeTagProps={{
            style: {
              fontSize: '14px',
              lineHeight: '1.5'
            }
          }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}

function InfoCard({ title, items }: Readonly<{ title: string; items: string[] }>) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-sm font-medium'>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className='space-y-2'>
          {items.map((item, index) => (
            <li key={index} className='text-syft-muted flex items-center gap-2 text-sm'>
              <Check className='h-4 w-4 text-green-500' />
              {item}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ResourceLink({ label }: Readonly<{ label: string }>) {
  return (
    <a
      href='#'
      className='text-syft-muted hover:bg-syft-surface hover:text-syft-primary flex items-center justify-between rounded p-2 text-sm transition-colors'
    >
      {label}
      <ArrowRight className='h-4 w-4 opacity-50' />
    </a>
  );
}
