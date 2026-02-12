/**
 * WorkflowDisplay Component
 *
 * Presents the workflow UI for processing status and streaming response.
 * Can be rendered as an overlay (for Hero) or inline (for ChatView).
 */
import { memo } from 'react';

import type { UseChatWorkflowReturn } from '@/hooks/use-chat-workflow';

import { AnimatePresence, motion } from 'framer-motion';

import { SourcesSection } from '@/components/chat/sources-section';
import { StatusIndicator } from '@/components/chat/status-indicator';

import { MarkdownMessage } from '../chat/markdown-message';

// =============================================================================
// Types
// =============================================================================

export interface WorkflowDisplayProps {
  /** Workflow state and actions from useChatWorkflow */
  workflow: UseChatWorkflowReturn;
  /** Display mode: overlay (modal-like) or inline (in message list) */
  mode: 'overlay' | 'inline';
  /** Whether to show the streamed response (for overlay mode) */
  showResponse?: boolean;
}

// =============================================================================
// Component
// =============================================================================

/**
 * Displays the workflow UI based on the current phase.
 *
 * - `preparing` / `streaming` phase: Shows StatusIndicator + streamed content
 * - `complete` phase: Shows final response with sources
 */
export const WorkflowDisplay = memo(function WorkflowDisplay({
  workflow,
  mode,
  showResponse = true
}: Readonly<WorkflowDisplayProps>) {
  const isInline = mode === 'inline';

  // Determine what to show based on workflow phase
  const showProcessing = workflow.phase === 'preparing' || workflow.phase === 'streaming';
  const showComplete = workflow.phase === 'complete';
  const showError = workflow.phase === 'error';

  // Don't render if idle
  if (workflow.phase === 'idle') {
    return null;
  }

  const content = (
    <>
      {/* Processing Status */}
      {showProcessing && workflow.processingStatus && (
        <div className={isInline ? 'max-w-2xl' : ''}>
          <StatusIndicator status={workflow.processingStatus} />
        </div>
      )}

      {/* Streamed Content (during streaming or after complete) */}
      {showResponse && (showProcessing || showComplete) && workflow.streamedContent && (
        <div
          className={`font-inter border-border bg-muted text-foreground rounded-2xl rounded-bl-none border px-5 py-3 shadow-sm ${
            isInline ? 'max-w-2xl' : ''
          }`}
        >
          <MarkdownMessage content={workflow.streamedContent} />
        </div>
      )}

      {/* Sources Section (after complete) */}
      {showComplete && Object.keys(workflow.aggregatorSources).length > 0 && (
        <div className={isInline ? 'mt-2 max-w-2xl' : 'mt-2'}>
          <SourcesSection sources={workflow.aggregatorSources} />
        </div>
      )}

      {/* Error Display */}
      {showError && workflow.error && (
        <div
          className={`font-inter rounded-2xl rounded-bl-none border border-red-200 bg-red-50 px-5 py-3 text-red-700 shadow-sm dark:border-red-800 dark:bg-red-950 dark:text-red-300 ${
            isInline ? 'max-w-2xl' : ''
          }`}
        >
          {workflow.error}
        </div>
      )}
    </>
  );

  // Inline mode: just render the content
  if (isInline) {
    return <div className='flex flex-col items-start space-y-2'>{content}</div>;
  }

  // Overlay mode: render with backdrop and modal styling
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className='fixed inset-0 z-50 flex items-center justify-center bg-black/20 p-6 backdrop-blur-sm'
      >
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.96 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className='w-full max-w-3xl'
        >
          {content}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
});

// =============================================================================
// Specialized Wrappers
// =============================================================================

export interface WorkflowOverlayProps {
  workflow: UseChatWorkflowReturn;
}

/**
 * Overlay mode workflow display for Hero page.
 * Shows as a modal/overlay when workflow is active.
 */
export const WorkflowOverlay = memo(function WorkflowOverlay({
  workflow
}: Readonly<WorkflowOverlayProps>) {
  return <WorkflowDisplay workflow={workflow} mode='overlay' showResponse={true} />;
});

export interface WorkflowInlineProps {
  workflow: UseChatWorkflowReturn;
}

/**
 * Inline mode workflow display for ChatView page.
 * Renders inline within the message list.
 */
export const WorkflowInline = memo(function WorkflowInline({
  workflow
}: Readonly<WorkflowInlineProps>) {
  return (
    <WorkflowDisplay
      workflow={workflow}
      mode='inline'
      showResponse={false} // ChatView manages response display in messages
    />
  );
});
