import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import CliRetiredPage from '@/pages/cli-retired';

describe('CliRetiredPage', () => {
  it('tells an old CLI user the sign-in cannot complete and points at the Python SDK', () => {
    render(
      <MemoryRouter initialEntries={['/cli-setup?port=51234&state=abc']}>
        <CliRetiredPage />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: /the syft cli is retired/i })).toBeInTheDocument();
    expect(screen.getByText(/can no longer complete/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /get started with the python sdk/i })).toHaveAttribute(
      'href',
      '/build'
    );
    expect(screen.getByRole('link', { name: /read the guide/i })).toHaveAttribute(
      'href',
      expect.stringContaining('docs/python/guides/sdk.md')
    );
  });
});
