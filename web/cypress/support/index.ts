// Cypress support file for Presek
// This file is automatically included before each test file

// Import commands.js using esBuild here
import './commands'

// Alternatively, you can use CommonJS syntax
// require('./commands')

declare global {
  namespace Cypress {
    interface Chainable {
      // Custom commands can be added here
      login(email: string, password: string): Chainable<Element>
      getByTestId(id: string): Chainable<Element>
    }
  }
}

// Add custom commands
Cypress.Commands.add('getByTestId', { prevSubject: false }, (id: string) => {
  return cy.get(`[data-testid="${id}"]`)
})
