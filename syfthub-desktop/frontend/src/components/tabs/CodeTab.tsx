import { useCallback } from 'react';
import Editor from '@monaco-editor/react';
import { useAppStore } from '../../stores/appStore';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function CodeTab() {
  const { runnerCode, originalRunnerCode, setRunnerCode, saveRunnerCode, isSaving, selectedEndpointDetail } = useAppStore();

  // Derive dirty state by comparing current vs original content
  const hasUnsavedChanges = runnerCode !== originalRunnerCode;

  const handleEditorChange = useCallback(
    (value: string | undefined) => {
      if (value !== undefined) {
        setRunnerCode(value);
      }
    },
    [setRunnerCode]
  );

  const handleSave = async () => {
    try {
      await saveRunnerCode();
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
    [saveRunnerCode]
  );

  if (!selectedEndpointDetail) {
    return null;
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Toolbar */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-border/50 bg-card/30">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">runner.py</span>
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

      {/* Editor */}
      <div className="flex-1 overflow-hidden">
        <Editor
          height="100%"
          language="python"
          theme="vs-dark"
          value={runnerCode}
          onChange={handleEditorChange}
          onMount={handleEditorMount}
          loading={
            <div className="h-full flex items-center justify-center bg-background text-muted-foreground">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-secondary border-t-primary rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm">Loading editor...</p>
              </div>
            </div>
          }
          options={{
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Fira Code', Consolas, monospace",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            padding: { top: 16, bottom: 16 },
            lineNumbers: 'on',
            glyphMargin: false,
            folding: true,
            lineDecorationsWidth: 10,
            lineNumbersMinChars: 3,
            renderLineHighlight: 'line',
            scrollbar: {
              vertical: 'auto',
              horizontal: 'auto',
              verticalScrollbarSize: 8,
              horizontalScrollbarSize: 8,
            },
            automaticLayout: true,
            wordWrap: 'on',
            tabSize: 4,
            insertSpaces: true,
          }}
        />
      </div>

      {/* Status bar */}
      <div className="flex-shrink-0 px-4 py-1.5 border-t border-border/50 bg-card/30 text-xs text-muted-foreground flex items-center justify-between">
        <span>Python</span>
        <span className="text-muted-foreground/70">Ctrl+S to save</span>
      </div>
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
