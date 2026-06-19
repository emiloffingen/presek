const captures = [
  { locale: 'sr', url: 'https://presek.live/' },
  { locale: 'mk', url: 'https://presek.mk/' },
]

const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
]

describe('fresh UI screenshots', () => {
  for (const capture of captures) {
    for (const viewport of viewports) {
      it(`${capture.locale} ${viewport.name}`, () => {
        cy.viewport(viewport.width, viewport.height)
        cy.visit(capture.url)
        cy.document().its('readyState').should('eq', 'complete')
        cy.wait(3000)
        cy.screenshot(`fresh-2026-06-19/${capture.locale}-${viewport.name}-viewport`, {
          capture: 'viewport',
          overwrite: true,
        })
        cy.screenshot(`fresh-2026-06-19/${capture.locale}-${viewport.name}-full`, {
          capture: 'fullPage',
          overwrite: true,
        })
      })
    }
  }
})
