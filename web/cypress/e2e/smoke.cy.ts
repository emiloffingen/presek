/// <reference types="cypress" />

describe('Presek Smoke Tests', () => {
  beforeEach(() => {
    cy.visit('/')
  })

  it('loads the homepage', () => {
    cy.contains('Пресек').should('be.visible')
  })

  it('has working navigation', () => {
    cy.get('nav').should('exist')
  })

  it('displays news feed', () => {
    cy.get('[data-testid="news-feed"]').should('exist')
    cy.get('[data-testid="article-card"]').should('have.length.gt', 0)
  })

  it('search functionality works', () => {
    cy.get('[data-testid="search-input"]').type('Македонија')
    cy.get('[data-testid="search-button"]').click()
    cy.url().should('include', '/search')
    cy.contains('Македонија').should('be.visible')
  })

  it('cluster page loads', () => {
    cy.get('[data-testid="cluster-link"]').first().click()
    cy.url().should('include', '/cluster/')
    cy.contains('Кластер').should('be.visible')
  })
})
