/// <reference types="cypress" />

const stubSuggestions = {
  clusters: [
    {
      cluster_id: 'search-test-cluster-1',
      synthetic_headline: 'Srbija: test vest o pretrazi',
      representative_image: '',
      has_synthesis: false,
      is_breaking: false,
      pulse_score: 0.85,
      articles: [
        {
          source: 'Test izvor',
          category: 'Srbija',
          image_url: '',
          title: 'Srbija vest',
        },
      ],
    },
  ],
  entity: null,
}

describe('Search command palette', () => {
  beforeEach(() => {
    cy.intercept('GET', '/api/trending?*', []).as('trending')
    cy.intercept('GET', '/api/news?*', stubSuggestions).as('searchSuggestions')

    cy.visit('/')
    cy.window().then((win) => {
      win.localStorage.clear()
      win.sessionStorage.clear()
    })
    cy.getByTestId('search-trigger').should('be.visible').click()
    cy.get('[data-testid="search-input"]', { timeout: 20000 }).should('be.visible')
  })

  it('opens the search bar, returns suggestions, and does not 500', () => {
    cy.getByTestId('search-input').type('Srbija')
    cy.wait('@searchSuggestions')
      .its('response.statusCode')
      .should('be.within', 200, 399)

    cy.getByTestId('search-results').should('be.visible')
    cy.getByTestId('search-result-cluster')
      .should('have.length.greaterThan', 0)
      .and('be.visible')
    cy.getByTestId('search-result-cluster')
      .first()
      .should('contain', 'Srbija')

    cy.get('body').should('not.contain', '500')
    cy.get('body').should('not.contain', 'Greška')
  })

  it('does not 500 when the country category filter is active without a timespan', () => {
    // This exercises the previous malformed-SQL bug where /api/news?q=...
    // returned 500 when category=country was sent without an explicit timespan.
    cy.getByTestId('search-filter-toggle').click()
    cy.get('[data-testid="search-category-chip"][data-category="country"]')
      .should('be.visible')
      .click()

    cy.getByTestId('search-input').type('Vučić')
    cy.wait('@searchSuggestions')
      .its('response.statusCode')
      .should('eq', 200)

    cy.getByTestId('search-results').should('be.visible')
    cy.get('body').should('not.contain', '500')
    cy.get('body').should('not.contain', 'Greška')
  })
})
