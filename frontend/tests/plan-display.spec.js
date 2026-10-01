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

test('waits for Groq retry time and keeps a failed message available', async ({ page }) => {
  let calls = 0
  await page.route('**/api/chat', route => {
    calls += 1
    return route.fulfill(calls === 1
      ? { status: 429, contentType: 'application/json', headers: { 'Retry-After': '2' }, body: JSON.stringify({ detail: 'Groq has reached a usage limit. Please retry in 2 seconds.' }) }
      : { status: 200, contentType: 'application/json', body: JSON.stringify({ session_id: sessionId, reply: 'A relaxed Lisbon plan.' }) })
  })
  await page.goto('/')
  await page.locator('#message').fill('Plan a trip to Lisbon, Portugal')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('alert')).toContainText('Groq has reached a usage limit')
  const retry = page.getByRole('button', { name: /Retry in|Retry message/ })
  await expect(retry).toBeDisabled()
  await expect(retry).toBeEnabled({ timeout: 5000 })
  await retry.click()
  await expect(page.locator('.message.assistant')).toContainText('A relaxed Lisbon plan.')
  expect(calls).toBe(2)
})
