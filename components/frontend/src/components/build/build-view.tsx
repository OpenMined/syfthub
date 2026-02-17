import React, { memo, Suspense, useCallback, useState } from 'react';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import Box from 'lucide-react/dist/esm/icons/box';
import Check from 'lucide-react/dist/esm/icons/check';
import Code2 from 'lucide-react/dist/esm/icons/code-2';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Terminal from 'lucide-react/dist/esm/icons/terminal';
import { PrismLight as SyntaxHighlighterBase } from 'react-syntax-highlighter';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

// Register languages for syntax highlighting (prism-light requires explicit registration)
SyntaxHighlighterBase.registerLanguage('bash', bash);
SyntaxHighlighterBase.registerLanguage('python', python);
SyntaxHighlighterBase.registerLanguage('typescript', typescript);
SyntaxHighlighterBase.registerLanguage('json', json);

// Wrap in lazy for code-splitting (the component itself is small, languages are registered above)
const SyntaxHighlighter = React.lazy(() => Promise.resolve({ default: SyntaxHighlighterBase }));

// Lazy load the style - will be loaded alongside SyntaxHighlighter
const loadStyle = () =>
  import('react-syntax-highlighter/dist/esm/styles/prism/vsc-dark-plus').then(
    (module_) => module_.default
  );

interface BuildViewProperties {
  onAuthRequired?: () => void;
}

export function BuildView({ onAuthRequired: _onAuthRequired }: Readonly<BuildViewProperties>) {
  return (
    <div className='bg-background min-h-screen'>
      <PageHeader title='Build' path='~/build' />

      {/* Main Content */}
      <div className='mx-auto max-w-5xl space-y-8 px-6 py-8'>
        {/* Hero / Intro Section */}
        <div className='max-w-3xl space-y-4'>
          <div className='bg-muted text-muted-foreground inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium'>
            <Code2 className='h-3 w-3' />
            Developer Portal
          </div>
          <h1 className='font-rubik text-foreground text-3xl font-medium'>
            Build privacy-first AI apps
          </h1>
          <p className='font-inter text-muted-foreground text-lg leading-relaxed'>
            Access high-value data and models you don't own through a unified, permissioned API.
            Choose your stack and start building in minutes.
          </p>
        </div>

        {/* Tabs Section */}
        <Tabs defaultValue='python' className='space-y-8'>
          <div className='flex items-center justify-between overflow-x-auto pb-2'>
            <TabsList className='border-border bg-muted h-auto flex-shrink-0 border p-1'>
              <TabsTrigger
                value='python'
                className='text-muted-foreground data-[state=active]:text-foreground data-[state=active]:bg-card px-4 py-2'
              >
                Python SDK
              </TabsTrigger>
              <TabsTrigger
                value='javascript'
                className='text-muted-foreground data-[state=active]:text-foreground data-[state=active]:bg-card px-4 py-2'
              >
                JavaScript SDK
              </TabsTrigger>
              <TabsTrigger
                value='mcp'
                className='text-muted-foreground data-[state=active]:text-foreground data-[state=active]:bg-card px-4 py-2'
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
                    'Browse and search endpoints',
                    'Manage your endpoints',
                    'Make distributed RAG queries',
                    'Authenticate and track usage'
                  ]}
                />
                <Card>
                  <CardHeader>
                    <CardTitle className='text-sm font-medium'>Resources</CardTitle>
                  </CardHeader>
                  <CardContent className='grid gap-2'>
                    <ResourceLink
                      label='Documentation'
                      href='https://syft.docs.openmined.org/sdk/python'
                    />
                    <ResourceLink
                      label='PyPI Package'
                      href='https://pypi.org/project/syfthub-sdk/'
                    />
                    <ResourceLink
                      label='GitHub Repository'
                      href='https://github.com/OpenMined/syfthub/tree/main/sdk/python'
                    />
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
                    'Browse and search endpoints',
                    'Manage your endpoints',
                    'Make distributed RAG queries',
                    'Authenticate and track usage'
                  ]}
                />
                <Card>
                  <CardHeader>
                    <CardTitle className='text-sm font-medium'>Resources</CardTitle>
                  </CardHeader>
                  <CardContent className='grid gap-2'>
                    <ResourceLink
                      label='Documentation'
                      href='https://syft.docs.openmined.org/sdk/typescript'
                    />
                    <ResourceLink
                      label='npm Package'
                      href='https://www.npmjs.com/package/@syfthub/sdk'
                    />
                    <ResourceLink
                      label='GitHub Repository'
                      href='https://github.com/OpenMined/syfthub/tree/main/sdk/typescript'
                    />
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
                  title='Claude Desktop Configuration'
                  description='Add SyftHub remote MCP server to your Claude Desktop settings.'
                  icon={<Box className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`{
  "mcpServers": {
    "syfthub": {
      "url": "https://syfthub.openmined.org/mcp"
    }
  }
}`}
                    language='json'
                  />
                </Section>

                <Section
                  title='Claude Code MCP Installation'
                  description='Add SyftHub MCP server to Claude Code CLI.'
                  icon={<Terminal className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`claude mcp add --transport http syfthub https://syfthub.openmined.org/mcp`}
                    language='bash'
                  />
                </Section>

                <div className='flex gap-4 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950/30'>
                  <div className='min-w-[24px] pt-1'>
                    <div className='flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600 dark:bg-blue-900 dark:text-blue-300'>
                      i
                    </div>
                  </div>
                  <div>
                    <h4 className='mb-1 font-medium text-blue-900 dark:text-blue-300'>
                      What is MCP?
                    </h4>
                    <p className='text-sm text-blue-700 dark:text-blue-400'>
                      The Model Context Protocol (MCP) allows AI assistants like Claude to directly
                      browse and interact with SyftHub endpoints during conversation. Once
                      configured, you can ask your AI to explore available models and data sources
                      in real-time using our remote MCP server at https://syfthub.openmined.org
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
                    <ResourceLink
                      label='Documentation'
                      href='https://syft.docs.openmined.org/mcp'
                    />
                    <ResourceLink
                      label='MCP Specification'
                      href='https://modelcontextprotocol.io/introduction'
                    />
                    <ResourceLink
                      label='GitHub Repository'
                      href='https://github.com/OpenMined/syfthub'
                    />
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

// Memoized Section component to prevent unnecessary re-renders
const Section = memo(function Section({
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
        <div className='border-border text-foreground bg-card rounded-lg border p-2'>{icon}</div>
        <div>
          <h3 className='text-foreground text-lg font-medium'>{title}</h3>
          <p className='text-muted-foreground text-sm'>{description}</p>
        </div>
      </div>
      {children}
    </div>
  );
});

// Memoized CodeBlock component with lazy-loaded syntax highlighter
const CodeBlock = memo(function CodeBlock({
  code,
  language
}: Readonly<{ code: string; language: string }>) {
  const [copied, setCopied] = useState(false);
  const [style, setStyle] = useState<Record<string, React.CSSProperties> | null>(null);

  // Load style on mount using lazy initialization
  React.useEffect(() => {
    let mounted = true;
    void loadStyle().then((loadedStyle) => {
      if (mounted) setStyle(loadedStyle);
    });
    return () => {
      mounted = false;
    };
  }, []);

  const copyToClipboard = useCallback(() => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  }, [code]);

  // Custom style to match the existing dark theme
  const customStyle = React.useMemo(() => {
    if (!style) return {};
    return {
      ...style,
      'pre[class*="language-"]': {
        ...(style['pre[class*="language-"]'] as React.CSSProperties | undefined),
        background: 'transparent',
        margin: 0,
        padding: 0,
        fontSize: '14px',
        lineHeight: '1.5'
      },
      'code[class*="language-"]': {
        ...(style['code[class*="language-"]'] as React.CSSProperties | undefined),
        background: 'transparent',
        fontSize: '14px',
        lineHeight: '1.5'
      }
    };
  }, [style]);

  return (
    <div className='group border-border relative overflow-hidden rounded-xl border bg-[#1a1923]'>
      <div className='absolute top-2 right-2 opacity-0 transition-opacity group-hover:opacity-100'>
        <Button
          variant='ghost'
          size='icon'
          className='text-muted-foreground h-8 w-8 hover:bg-white/10 hover:text-white'
          onClick={copyToClipboard}
        >
          {copied ? <Check className='h-4 w-4' /> : <Copy className='h-4 w-4' />}
        </Button>
      </div>
      <div className='flex items-center justify-between border-b border-white/5 bg-[#131219] px-4 py-2'>
        <span className='text-muted-foreground font-mono text-xs'>{language}</span>
      </div>
      <div className='overflow-x-auto p-4'>
        <Suspense fallback={<pre className='text-muted-foreground font-mono text-sm'>{code}</pre>}>
          {style ? (
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
          ) : (
            <pre className='text-muted-foreground font-mono text-sm'>{code}</pre>
          )}
        </Suspense>
      </div>
    </div>
  );
});

// Memoized InfoCard component
const InfoCard = memo(function InfoCard({
  title,
  items
}: Readonly<{ title: string; items: string[] }>) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-sm font-medium'>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className='space-y-2'>
          {items.map((item, index) => (
            <li key={index} className='text-muted-foreground flex items-center gap-2 text-sm'>
              <Check className='h-4 w-4 text-green-500' />
              {item}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
});

// Memoized ResourceLink component
const ResourceLink = memo(function ResourceLink({
  label,
  href
}: Readonly<{ label: string; href: string }>) {
  return (
    <a
      href={href}
      target='_blank'
      rel='noopener noreferrer'
      className='text-muted-foreground hover:bg-muted hover:text-foreground flex items-center justify-between rounded p-2 text-sm transition-colors'
    >
      {label}
      <ArrowRight className='h-4 w-4 opacity-50' />
    </a>
  );
});
