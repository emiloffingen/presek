/// <reference types="cypress" />

describe('Presek Smoke Tests', () => {
  it('loads the Serbian homepage', () => {
    cy.visit('/')
    cy.contains('Presek').should('be.visible')
  })

  it('loads the Macedonian homepage', () => {
    cy.visit('/mk/', {
      headers: {
        Host: 'presek.live',
      },
    })
    cy.contains('Presek').should('be.visible')
    cy.get('[data-testid="news-feed"]').should('exist')
  })

  it('loads the briefing page', () => {
    cy.visit('/briefing')
    cy.get('main').should('exist')
  })

  beforeEach(() => {
    cy.visit('/')
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
    cy.get('[data-testid="cluster-link"]').filter(':visible').first().then(($link) => {
      if (!$link.length) {
        cy.log('No cluster links on homepage — skipping MK narrative toggle test')
        return
      }

      const href = $link.attr('href')
      if (!href) {
        cy.log('Cluster link has no href — skipping MK narrative toggle test')
        return
      }

      cy.visit(href, {
        headers: {
          'Host': 'presek.mk',
        },
      })

      cy.get('.narrative-body').should('have.class', 'is-collapsed')
      cy.get('.narrative-toggle').should('be.visible').click()
      cy.get('.narrative-body').should('not.have.class', 'is-collapsed')
      cy.get('.narrative-toggle').should('not.be.visible')
    })
  })
})
