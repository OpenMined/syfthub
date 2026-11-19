import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QuerySchemaCard } from '@/components/endpoint/query-schema-card';

const schema = {
  metadata_fields: ['title', 'published', 'tags', 'author', 'url', 'source', 'doc_id'],
  filters: {
    fields: {
      published: { type: 'datetime', ops: ['gt', 'lt'] },
      tags: { type: 'string[]', ops: ['contains_any'] }
    },
    logic: ['and', 'or'],
    max_depth: 5,
    max_conditions: 50,
    max_list_values: 100
  }
};

const names = () =>
  screen
    .getAllByText(/^[a-z_]+$/)
    .map((element) => element.textContent)
    .filter((text) => text !== 'Metadata');

describe('QuerySchemaCard', () => {
  it('sorts the fields, shows five, and expands on request', () => {
    render(<QuerySchemaCard schema={schema} endpointType='data_source' />);
    expect(names()).toEqual(['author', 'doc_id', 'published', 'source', 'tags']);
    fireEvent.click(screen.getByRole('button', { name: '+2 more' }));
    expect(names()).toEqual(['author', 'doc_id', 'published', 'source', 'tags', 'title', 'url']);
    fireEvent.click(screen.getByRole('button', { name: 'Show less' }));
    expect(names()).toHaveLength(5);
  });

  it('marks the filterable fields and counts them', () => {
    render(<QuerySchemaCard schema={schema} endpointType='data_source' />);
    expect(screen.getByText('2 of 7 filterable')).toBeInTheDocument();
    expect(screen.getAllByLabelText('filterable')).toHaveLength(2);
    expect(screen.getByText('tags').closest('div')).toHaveAttribute('title', 'string[]');
    expect(screen.getByText('author').closest('div')).not.toHaveAttribute('title');
    expect(screen.queryByText('contains_any')).not.toBeInTheDocument();
  });

  it('says so when the owner disabled filtering', () => {
    render(
      <QuerySchemaCard
        schema={{ ...schema, filters: { ...schema.filters, fields: {} } }}
        endpointType='data_source'
      />
    );
    expect(screen.getByText('0 of 7 filterable')).toBeInTheDocument();
    expect(screen.queryAllByLabelText('filterable')).toHaveLength(0);
    fireEvent.focus(screen.getByRole('button', { name: 'About metadata' }));
    expect(screen.getAllByText(/has not enabled filtering/)[0]).toBeInTheDocument();
  });

  it('shows no filter count for a space that predates filters', () => {
    render(
      <QuerySchemaCard
        schema={{ metadata_fields: ['title'], filters: null }}
        endpointType='data_source'
      />
    );
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.queryByText(/filterable$/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /more/ })).not.toBeInTheDocument();
  });

  it('renders nothing without a schema, without fields, or for a model', () => {
    const { container } = render(<QuerySchemaCard schema={null} endpointType='data_source' />);
    expect(container).toBeEmptyDOMElement();
    const empty = render(
      <QuerySchemaCard
        schema={{ metadata_fields: [], filters: schema.filters }}
        endpointType='data_source'
      />
    );
    expect(empty.container).toBeEmptyDOMElement();
    const model = render(<QuerySchemaCard schema={schema} endpointType='model' />);
    expect(model.container).toBeEmptyDOMElement();
  });
});
