import { useState, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import DOMPurify from 'dompurify';
import { useAppStore } from '../../stores/appStore';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function DocsTab() {
  const { readmeContent, originalReadmeContent, setReadmeContent, saveReadme, isSaving, selectedEndpointDetail } = useAppStore();
  const [viewMode, setViewMode] = useState<'edit' | 'preview'>('preview');

  // Derive dirty state by comparing current vs original content
  const hasUnsavedChanges = readmeContent !== originalReadmeContent;

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      if (value !== undefined) {
        setReadmeContent(value);
      }
    },
    [setReadmeContent]
  );

  const handleSave = async () => {
    try {
      await saveReadme();
    } catch {
      // Error is handled by the store
    }
  };

  // Keyboard shortcut for save
  const handleEditorMount = useCallback(
    (editor: { addCommand: (keybinding: number, handler: () => void) => void }, monaco: { KeyMod: { CtrlCmd: number }; KeyCode: { KeyS: number } }) => {
      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        handleSave();
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [saveReadme]
  );

  if (!selectedEndpointDetail) {
    return null;
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Toolbar */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-border/50 bg-card/30">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">README.md</span>
          {hasUnsavedChanges && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="w-2 h-2 rounded-full bg-chart-3" />
              </TooltipTrigger>
              <TooltipContent side="top">
                <p>Unsaved changes</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex items-center bg-card rounded-md p-0.5">
            <button
              onClick={() => setViewMode('edit')}
              className={`px-2.5 py-1 text-xs rounded transition-colors ${
                viewMode === 'edit'
                  ? 'bg-secondary text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Edit
            </button>
            <button
              onClick={() => setViewMode('preview')}
              className={`px-2.5 py-1 text-xs rounded transition-colors ${
                viewMode === 'preview'
                  ? 'bg-secondary text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Preview
            </button>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleSave}
            disabled={isSaving || !hasUnsavedChanges}
            className="h-7 text-xs"
          >
            {isSaving ? (
              <>
                <span className="w-3 h-3 border border-muted-foreground border-t-transparent rounded-full animate-spin mr-1.5" />
                Saving...
              </>
            ) : (
              <>
                <SaveIcon className="w-3.5 h-3.5 mr-1.5" />
                Save
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {viewMode === 'edit' ? (
          <Editor
            height="100%"
            language="markdown"
            theme="vs-dark"
            value={readmeContent}
            onChange={handleEditorChange}
            onMount={handleEditorMount}
            options={{
              fontSize: 14,
              fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              padding: { top: 16, bottom: 16 },
              lineNumbers: 'off',
              glyphMargin: false,
              folding: true,
              lineDecorationsWidth: 0,
              renderLineHighlight: 'none',
              scrollbar: {
                vertical: 'auto',
                horizontal: 'auto',
                verticalScrollbarSize: 8,
                horizontalScrollbarSize: 8,
              },
              automaticLayout: true,
              wordWrap: 'on',
              tabSize: 2,
              insertSpaces: true,
            }}
          />
        ) : (
          <MarkdownPreview content={readmeContent} />
        )}
      </div>

      {/* Status bar */}
      <div className="flex-shrink-0 px-4 py-1.5 border-t border-border/50 bg-card/30 text-xs text-muted-foreground flex items-center justify-between">
        <span>Markdown</span>
        <span className="text-muted-foreground/70">Ctrl+S to save</span>
      </div>
    </div>
  );
}

// Simple markdown preview with DOMPurify sanitization
function MarkdownPreview({ content }: { content: string }) {
  // Basic markdown to HTML conversion - using Tailwind prose classes for styling
  const rawHtml = content
    // Headers
    .replace(/^### (.*$)/gm, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.*$)/gm, '<h2 class="text-xl font-semibold mt-6 mb-3">$1</h2>')
    .replace(/^# (.*$)/gm, '<h1 class="text-2xl font-bold mt-6 mb-4">$1</h1>')
    // Bold
    .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
    // Italic
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-card rounded-lg p-4 my-4 overflow-x-auto"><code class="text-sm">$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-card px-1.5 py-0.5 rounded text-sm">$1</code>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-primary hover:underline">$1</a>')
    // Lists
    .replace(/^\* (.*$)/gm, '<li class="ml-4">$1</li>')
    .replace(/^- (.*$)/gm, '<li class="ml-4">$1</li>')
    // Paragraphs
    .replace(/\n\n/g, '</p><p class="my-3">')
    // Line breaks
    .replace(/\n/g, '<br />');

  // Sanitize HTML using DOMPurify
  const sanitizedHtml = DOMPurify.sanitize(`<p class="my-3">${rawHtml}</p>`, {
    ADD_ATTR: ['class'],
    ADD_TAGS: ['pre', 'code'],
  });

  if (!content.trim()) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground">
        <div className="text-center">
          <p className="text-sm">No README content</p>
          <p className="text-xs mt-1">Switch to Edit mode to add documentation</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div
        className="prose prose-invert max-w-none"
        dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
      />
    </div>
  );
}

function SaveIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
    </svg>
  );
}
