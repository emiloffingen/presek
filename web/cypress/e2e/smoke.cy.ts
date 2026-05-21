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
})
