import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QuerySchemaCard } from '@/components/endpoint/query-schema-card';

const schema = {
  metadata_fields: ['title', 'published'],
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

describe('QuerySchemaCard', () => {
  it('lists the returned keys and the filterable fields with their types', () => {
    render(<QuerySchemaCard schema={schema} endpointType='data_source' />);
    expect(screen.getByText('Metadata')).toBeInTheDocument();
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('tags')).toBeInTheDocument();
    expect(screen.getByText('string[]')).toBeInTheDocument();
    expect(screen.queryByText('contains_any')).not.toBeInTheDocument();
  });

  it('says so when the owner disabled filtering', () => {
    render(
      <QuerySchemaCard
        schema={{ ...schema, filters: { ...schema.filters, fields: {} } }}
        endpointType='data_source'
      />
    );
    expect(screen.getByText('Queries cannot filter this source')).toBeInTheDocument();
  });

  it('shows no filter section for a space that predates filters', () => {
    render(
      <QuerySchemaCard
        schema={{ metadata_fields: ['title'], filters: null }}
        endpointType='data_source'
      />
    );
    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.queryByText('Filterable')).not.toBeInTheDocument();
  });

  it('renders nothing without a schema or for a model', () => {
    const { container } = render(<QuerySchemaCard schema={null} endpointType='data_source' />);
    expect(container).toBeEmptyDOMElement();
    const model = render(<QuerySchemaCard schema={schema} endpointType='model' />);
    expect(model.container).toBeEmptyDOMElement();
  });
});
