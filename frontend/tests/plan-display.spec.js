import { test, expect } from '@playwright/test'

const sessionId = '550e8400-e29b-41d4-a716-446655440000'
const bhopal = [
  '| Day | Activities | Transport | Day-wise Cost |',
  '| --- | --- | --- | --- |',
  ...Array.from({ length: 5 }, (_, i) => `| Day ${i + 1} | Upper Lake, Bhopal heritage walking route and local food stop | Shared auto-rickshaw and local bus | ₹1,250–₹2,000 |`),
].join('\n')
const international = [
  '| Day | Places and activities | Transport | Estimated local cost |',
  '| --- | --- | --- | --- |',
  ...Array.from({ length: 7 }, (_, i) => `| Day ${i + 1} | São Bento railway station, Porto, Portugal, plus the long Ribeira waterfront promenade | Metro and regional train with luggage | €120–€180 per person |`),
].join('\n')

for (const [name, viewport] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
  for (const [planName, plan, count] of [['bhopal', bhopal, 5], ['international', international, 7]]) {
    test(`${planName} itinerary stays readable on ${name}`, async ({ page }) => {
      await page.setViewportSize(viewport)
      await page.route('**/api/chat', route => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ session_id: sessionId, reply: plan }),
      }))
      await page.goto('/')
      await page.locator('#message').fill(`Plan a ${planName} trip`)
      await page.getByRole('button', { name: 'Send message' }).click()
      await expect(page.locator('.itinerary-day')).toHaveCount(count)
      await expect(page.locator('.itinerary-day').first()).toContainText(planName === 'bhopal' ? '₹1,250–₹2,000' : '€120–€180')
      const dimensions = await page.evaluate(() => ({
        pageWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        cardWidth: document.querySelector('.itinerary-day').getBoundingClientRect().width,
      }))
      expect(dimensions.pageWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
      expect(dimensions.cardWidth).toBeGreaterThan(name === 'mobile' ? 260 : 300)
      await page.screenshot({ path: `test-results/${planName}-${name}.png`, fullPage: true })
    })
  }
}
