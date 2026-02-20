import type { ChatSource } from '@/lib/types';
import type { ReactNode } from 'react';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ModelSelector } from '@/components/chat/model-selector';
import { createMockChatSource } from '@/test/mocks/fixtures';

vi.mock('framer-motion', () => import('@/test/mocks/framer-motion'));

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

describe('ModelSelector', () => {
  const models: ChatSource[] = [
    createMockChatSource({
      name: 'GPT-4',
      slug: 'gpt-4',
      description: 'OpenAI large language model',
      full_path: 'openai/gpt-4',
      stars_count: 10
    }),
    createMockChatSource({
      name: 'Claude 3',
      slug: 'claude-3',
      description: 'Anthropic model',
      full_path: 'anthropic/claude-3',
      stars_count: 0
    }),
    createMockChatSource({
      name: 'Llama 2',
      slug: 'llama-2',
      description: 'Meta open source model',
      full_path: 'meta/llama-2',
      stars_count: 5
    })
  ];

  let onModelSelect: (model: ChatSource) => void;

  beforeEach(() => {
    vi.clearAllMocks();
    onModelSelect = vi.fn();
  });

  function renderSelector(overrides?: {
    selectedModel?: ChatSource | null;
    models?: ChatSource[];
    isLoading?: boolean;
  }) {
    return render(
      <ModelSelector
        selectedModel={overrides?.selectedModel ?? null}
        onModelSelect={onModelSelect}
        models={overrides?.models ?? models}
        isLoading={overrides?.isLoading ?? false}
      />,
      { wrapper }
    );
  }

  it('shows selected model name', () => {
    renderSelector({ selectedModel: models[0] });
    expect(screen.getByText('GPT-4')).toBeInTheDocument();
  });

  it('shows placeholder when no model selected', () => {
    renderSelector();
    expect(screen.getByText('Select model')).toBeInTheDocument();
  });

  it('opens dropdown on click', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));

    expect(screen.getByPlaceholderText('Search models…')).toBeInTheDocument();
    // All models visible
    expect(screen.getByText('GPT-4')).toBeInTheDocument();
    expect(screen.getByText('Claude 3')).toBeInTheDocument();
    expect(screen.getByText('Llama 2')).toBeInTheDocument();
  });

  it('filters models by name', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));
    fireEvent.change(screen.getByPlaceholderText('Search models…'), {
      target: { value: 'GPT' }
    });

    expect(screen.getByText('GPT-4')).toBeInTheDocument();
    expect(screen.queryByText('Claude 3')).not.toBeInTheDocument();
    expect(screen.queryByText('Llama 2')).not.toBeInTheDocument();
  });

  it('filters models by description', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));
    fireEvent.change(screen.getByPlaceholderText('Search models…'), {
      target: { value: 'anthropic' }
    });

    expect(screen.queryByText('GPT-4')).not.toBeInTheDocument();
    expect(screen.getByText('Claude 3')).toBeInTheDocument();
  });

  it('filters models by slug', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));
    fireEvent.change(screen.getByPlaceholderText('Search models…'), {
      target: { value: 'llama-2' }
    });

    expect(screen.queryByText('GPT-4')).not.toBeInTheDocument();
    expect(screen.getByText('Llama 2')).toBeInTheDocument();
  });

  it('shows no results message when search finds nothing', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));
    fireEvent.change(screen.getByPlaceholderText('Search models…'), {
      target: { value: 'nonexistent' }
    });

    expect(screen.getByText('No models found')).toBeInTheDocument();
  });

  it('selects model and closes dropdown', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));

    const options = screen.getAllByRole('option');
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- getAllByRole guarantees results
    await user.click(options[0]!);

    expect(onModelSelect).toHaveBeenCalledWith(models[0]);
    // Dropdown should close
    expect(screen.queryByPlaceholderText('Search models…')).not.toBeInTheDocument();
  });

  it('shows selected indicator on current model', async () => {
    const user = userEvent.setup();
    renderSelector({ selectedModel: models[1] });

    // Open dropdown (trigger shows selected model name)
    await user.click(screen.getByRole('button', { name: /claude 3/i }));

    const options = screen.getAllByRole('option');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');
    expect(options[0]).toHaveAttribute('aria-selected', 'false');
  });

  it('closes dropdown on Escape key', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));
    expect(screen.getByPlaceholderText('Search models…')).toBeInTheDocument();

    await user.keyboard('{Escape}');

    expect(screen.queryByPlaceholderText('Search models…')).not.toBeInTheDocument();
  });

  it('closes dropdown on click outside', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));
    expect(screen.getByPlaceholderText('Search models…')).toBeInTheDocument();

    await user.click(document.body);

    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Search models…')).not.toBeInTheDocument();
    });
  });

  it('shows model count in footer', async () => {
    const user = userEvent.setup();
    renderSelector();

    await user.click(screen.getByText('Select model'));

    expect(screen.getByText('3 models available')).toBeInTheDocument();
  });

  it('disables trigger when loading', () => {
    renderSelector({ isLoading: true });
    const buttons = screen.getAllByRole('button');
    // The trigger button should be disabled
    expect(buttons[0]).toBeDisabled();
  });

  it('shows singular "model" for single model', async () => {
    const user = userEvent.setup();
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- test array with known index
    renderSelector({ models: [models[0]!] });

    await user.click(screen.getByText('Select model'));

    expect(screen.getByText('1 model available')).toBeInTheDocument();
  });
});
