import React from 'react';
import ResearchIsland from './ResearchIsland';

describe('<ResearchIsland />', () => {
  it('renders the ResearchIsland component', () => {
    // Mount the component
    cy.mount(
        <ResearchIsland 
            clusterId="test-cluster-123" 
            initialHeadline="Test News Headline" 
        />
    );

    // Verify UI components container
    cy.get('.research-analyst-container').should('be.visible');
  });

  it('shows loading state when a mode is selected', () => {
    cy.mount(
        <ResearchIsland 
            clusterId="test-cluster-123" 
            initialHeadline="Test News Headline" 
        />
    );

    // Mock fetch to prevent network calls and stay in loading state
    cy.intercept('GET', '/api/intelligence/cluster/test-cluster-123/research*', {
        delay: 5000,
        body: {}
    }).as('researchRequest');

    // Click the first research mode button
    cy.get('button').contains(/Istraži/i).first().click();
    
    // Check for the loading button attribute
    cy.get('button[aria-busy="true"]').should('exist');
  });

  it('renders API-returned content and suggestions', () => {
    const mockData = {
      status: 'success',
      mode: 'custom', // Trigger custom mode to show suggestions
      report: '## Header\nThis is a test report.',
      suggestions: ['Tell me more', 'What is the context?'],
    };

    cy.mount(
      <ResearchIsland 
          clusterId="test-cluster-123" 
          initialHeadline="Test News Headline" 
      />
    );

    // Mock successful API response
    cy.intercept('GET', '/api/intelligence/cluster/test-cluster-123/research*', {
      statusCode: 200,
      body: mockData
    }).as('researchRequest');

    // Trigger research
    cy.get('button').contains(/Istraži/i).first().click();
    cy.wait('@researchRequest');

    // Verify content rendering
    cy.contains('This is a test report.').should('be.visible');
    cy.contains('Tell me more').should('be.visible');
  });
});
