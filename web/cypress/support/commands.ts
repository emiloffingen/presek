// Custom Cypress commands for Presek

// Login command
Cypress.Commands.add('login', (email: string, password: string) => {
  cy.session([email, password], () => {
    cy.visit('/login')
    cy.get('input[type="email"]').type(email)
    cy.get('input[type="password"]').type(password)
    cy.get('button[type="submit"]').click()
    cy.url().should('include', '/')
  })
})

// Wait for API to be ready
Cypress.Commands.add('waitForAPI', () => {
  cy.request('GET', '/api/health').its('status').should('eq', 200)
})
