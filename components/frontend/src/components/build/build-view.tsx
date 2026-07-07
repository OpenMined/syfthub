import React, { memo, useCallback, useState } from 'react';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import Box from 'lucide-react/dist/esm/icons/box';
import Check from 'lucide-react/dist/esm/icons/check';
import Code2 from 'lucide-react/dist/esm/icons/code-2';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Terminal from 'lucide-react/dist/esm/icons/terminal';

import {
  CodeBlockCode,
  CodeBlockGroup,
  CodeBlock as CodeBlockRoot
} from '@/components/prompt-kit/code-block';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

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
            For Developers
          </div>
          <h1 className='font-rubik text-foreground text-3xl font-medium'>
            Tap into capabilities across the directory
          </h1>
          <p className='font-inter text-muted-foreground text-lg leading-relaxed'>
            Query data and models published by others — with attribution, compensation, and privacy
            built in. Pick your stack, explore what's available, and start experimenting.
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
                  description='One command to get started.'
                  icon={<Box className='h-5 w-5' />}
                >
                  <CodeBlock code='pip install syfthub-sdk' language='bash' />
                </Section>

                <Section
                  title='Explore & Query'
                  description='Browse what others have published and start experimenting.'
                  icon={<Terminal className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`from syfthub_sdk import SyftHubClient

# Connect to the directory
client = SyftHubClient(base_url="https://hub.syft.com")
user = client.auth.login(username="alice", password="secret123")

# Discover available data and models
for endpoint in client.hub.browse():
    print(f"{endpoint.path}: {endpoint.name}")

# Dig into a specific capability
endpoint = client.hub.get("alice/my-model")
print(endpoint.readme)`}
                    language='python'
                  />
                </Section>

                <Section
                  title='Publish Your Own'
                  description='Share your data or models so others can build with them.'
                  icon={<Code2 className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`# Publish a capability to the directory
endpoint = client.my_endpoints.create(
    name="My Model",
    visibility="public",
    description="A machine learning model",
    readme="# My Model\\n\\nDocumentation here."
)
print(f"Created: {endpoint.slug}")

# List your published capabilities
for ep in client.my_endpoints.list():
    print(f"{ep.name} ({ep.visibility})")`}
                    language='python'
                  />
                </Section>
              </div>

              <div className='space-y-6'>
                <InfoCard
                  title='What You Can Do'
                  items={[
                    'Discover data and models others have shared',
                    'Query capabilities with built-in privacy',
                    'Run distributed RAG across sources',
                    'Publish and manage your own endpoints'
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
                  description='One command to get started.'
                  icon={<Box className='h-5 w-5' />}
                >
                  <CodeBlock code='npm install @syfthub/sdk' language='bash' />
                </Section>

                <Section
                  title='Explore & Query'
                  description='Browse what others have published and start experimenting.'
                  icon={<Terminal className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`import { SyftHubClient } from '@syfthub/sdk';

// Connect to the directory
const client = new SyftHubClient({
  baseUrl: 'https://hub.syft.com'
});
const user = await client.auth.login('alice', 'secret123');

// Discover available data and models
for await (const endpoint of client.hub.browse()) {
  console.log(\`\${endpoint.ownerUsername}/\${endpoint.slug}: \${endpoint.name}\`);
}

// Dig into a specific capability
const endpoint = await client.hub.get('alice/my-model');
console.log(endpoint.readme);`}
                    language='typescript'
                  />
                </Section>

                <Section
                  title='Publish Your Own'
                  description='Share your data or models so others can build with them.'
                  icon={<Code2 className='h-5 w-5' />}
                >
                  <CodeBlock
                    code={`import { EndpointType, Visibility } from '@syfthub/sdk';

// Publish a capability to the directory
const endpoint = await client.myEndpoints.create({
  name: 'My Model',
  type: EndpointType.MODEL,
  visibility: Visibility.PUBLIC,
  description: 'A machine learning model',
  readme: '# My Model\\n\\nDocumentation here.',
});
console.log(\`Created: \${endpoint.slug}\`);

// List your published capabilities
for await (const ep of client.myEndpoints.list()) {
  console.log(\`\${ep.name} (\${ep.visibility})\`);
}`}
                    language='typescript'
                  />
                </Section>
              </div>

              <div className='space-y-6'>
                <InfoCard
                  title='What You Can Do'
                  items={[
                    'Discover data and models others have shared',
                    'Query capabilities with built-in privacy',
                    'Run distributed RAG across sources',
                    'Publish and manage your own endpoints'
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
                  description='Point Claude at the directory so it can discover and use capabilities for you.'
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
                  title='Claude Code'
                  description='One command to connect from the terminal.'
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
                    <h4 className='mb-1 font-medium text-blue-900 dark:text-blue-300'>Why MCP?</h4>
                    <p className='text-sm text-blue-700 dark:text-blue-400'>
                      MCP lets AI assistants like Claude browse and query the directory directly
                      during a conversation. Once connected, you can ask it to find relevant data or
                      models, run queries, and pull results — no code required.
                    </p>
                  </div>
                </div>
              </div>

              <div className='space-y-6'>
                <InfoCard
                  title='What You Can Do'
                  items={[
                    'Let your AI find relevant data and models',
                    'Query capabilities conversationally',
                    'Works with Claude Desktop & Claude Code'
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

        {/* Architecture Overview */}
        <section className='space-y-4 pt-4'>
          <h2 className='font-rubik text-foreground text-xl font-medium'>
            How it all fits together
          </h2>
          <p className='font-inter text-muted-foreground max-w-2xl text-sm leading-relaxed'>
            Syft Space nodes publish capabilities to the directory. SDKs and MCP let you discover
            and query them — data stays where it lives, you get the results.
          </p>
          <div className='border-border overflow-hidden rounded-xl border'>
            <a
              href='https://syft.docs.openmined.org/assets/fullsetup-CAbzIKrJ.png'
              target='_blank'
              rel='noopener noreferrer'
            >
              <img
                src='https://syft.docs.openmined.org/assets/fullsetup-CAbzIKrJ.png'
                alt='Syft full architecture setup diagram showing how Syft Space, the directory, and SDKs connect'
                className='w-full'
                loading='lazy'
              />
            </a>
          </div>
        </section>
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

// Memoized CodeBlock component using prompt-kit primitives with shiki highlighting
const CodeBlock = memo(function CodeBlock({
  code,
  language
}: Readonly<{ code: string; language: string }>) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = useCallback(() => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  }, [code]);

  return (
    <CodeBlockRoot className='bg-[#1a1923]'>
      <CodeBlockGroup className='border-b border-white/5 bg-[#131219] px-4 py-2'>
        <span className='text-muted-foreground font-mono text-xs'>{language}</span>
        <Button
          variant='ghost'
          size='icon'
          className='text-muted-foreground h-8 w-8 hover:bg-white/10 hover:text-white'
          onClick={copyToClipboard}
        >
          {copied ? <Check className='h-4 w-4' /> : <Copy className='h-4 w-4' />}
        </Button>
      </CodeBlockGroup>
      <CodeBlockCode code={code} language={language} theme='github-dark' />
    </CodeBlockRoot>
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
