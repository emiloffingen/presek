/// <reference types="cypress" />

describe('Presek Smoke Tests', () => {
  beforeEach(() => {
    cy.visit('/')
  })

  it('loads the homepage', () => {
    cy.contains('Presek').should('be.visible')
  })

  it('has working navigation', () => {
    cy.get('nav').should('exist')
  })

  it('displays news feed', () => {
    cy.get('[data-testid="news-feed"]').should('exist')
    cy.get('[data-testid="article-card"]').should('have.length.gt', 0)
  })

  it('search functionality works', () => {
    cy.get('[data-testid="search-trigger"]').click()
    cy.get('[data-testid="search-input"]').should('be.visible').type('Srbija{enter}')
    cy.get('.filter-title', { timeout: 10000 }).should('be.visible').and('contain', 'Srbija')
    cy.url().should('include', 'q=Srbija')
  })

  it('cluster page loads', () => {
    cy.get('[data-testid="cluster-link"]').filter(':visible').first().click()
    cy.url().should('include', '/cluster/')
    cy.contains('klaster').should('be.visible')
  })

  it('verifies the Macedonian cluster page toggle button works', () => {
    // Visit the specific Macedonian cluster page
    cy.visit('/mk/cluster/431641e7147e-dve-lica-lieni-od-sloboda-vkupno-etiri-prijavi-za-semejno-nasilstvo-vo-poslednoto-denonoie', {
      headers: {
        'Host': 'presek.mk'
      }
    })
    
    // Check that the narrative body starts as collapsed
    cy.get('.narrative-body').should('have.class', 'is-collapsed')
    
    // Click the toggle button
    cy.get('.narrative-toggle').should('be.visible').click()
    
    // Assert that the narrative body is no longer collapsed
    cy.get('.narrative-body').should('not.have.class', 'is-collapsed')
    cy.get('.narrative-toggle').should('not.be.visible')
  })
})
